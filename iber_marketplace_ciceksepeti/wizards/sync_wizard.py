from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberCiceksepetiSyncWizard(models.TransientModel):
    _name = 'iber.marketplace.ciceksepeti.sync.wizard'
    _description = 'Çiçeksepeti Senkronizasyon Sihirbazı'

    config_id = fields.Many2one(
        'iber.marketplace.ciceksepeti.config', required=True, string='Bağlantı')
    sync_type = fields.Selection([
        ('orders', 'Siparişler'),
        ('inventory', 'Stok / Fiyat'),
    ], required=True, default='orders', string='Senkronizasyon Türü')

    # Sipariş seçenekleri
    order_days_back = fields.Integer(
        default=7, string='Son N Gün',
        help='Kaç günlük siparişlerin çekileceği')
    order_status_filter = fields.Char(
        string='Durum Filtresi (boş=hepsi)',
        help='Örn: Created — tek durum için API parametresi')

    # Sonuç
    state = fields.Selection([
        ('draft', 'Hazır'),
        ('done', 'Tamamlandı'),
        ('error', 'Hata'),
    ], default='draft', readonly=True, string='Durum')
    result_message = fields.Text(readonly=True, string='Sonuç')

    # ------------------------------------------------------------------
    # Ana çalıştırıcı
    # ------------------------------------------------------------------

    def action_run(self):
        self.ensure_one()
        try:
            if self.sync_type == 'orders':
                self._sync_orders()
            elif self.sync_type == 'inventory':
                self._sync_inventory()
            self.write({'state': 'done'})
        except UserError:
            raise
        except Exception as exc:
            self.write({'state': 'error', 'result_message': str(exc)})
            raise UserError(_('Senkronizasyon hatası: %s') % exc)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Sipariş senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_orders(self):
        client = self.config_id._get_client()
        days = max(1, self.order_days_back or 7)

        now_dt = datetime.utcnow()
        start_dt = now_dt - timedelta(days=days)
        # Çiçeksepeti ISO8601 tarih formatı
        start_date = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_date = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        filters = {
            'startDate': start_date,
            'endDate': end_date,
        }
        if self.order_status_filter and self.order_status_filter.strip():
            filters['status'] = self.order_status_filter.strip()

        created = updated = page = 0
        Order = self.env['iber.marketplace.ciceksepeti.order']

        while True:
            try:
                data = client.get_orders(page=page, page_size=100, **filters)
            except Exception as exc:
                raise UserError(_('Çiçeksepeti sipariş çekme hatası: %s') % exc)

            content = data.get('content') or data.get('orders') or []
            if not content:
                break

            for raw in content:
                order_code = raw.get('orderCode') or raw.get('order_code') or ''
                if not order_code:
                    continue

                existing = Order.search([
                    ('config_id', '=', self.config_id.id),
                    ('order_code', '=', order_code),
                ], limit=1)

                vals = self._map_order_vals(raw)
                line_data = vals.pop('line_ids', [])

                if existing:
                    existing.write(vals)
                    existing.line_ids.unlink()
                    for ld in line_data:
                        ld[2]['order_id'] = existing.id
                        self.env['iber.marketplace.ciceksepeti.order.line'].create(ld[2])
                    updated += 1
                else:
                    vals['config_id'] = self.config_id.id
                    order = Order.create(vals)
                    for ld in line_data:
                        ld[2]['order_id'] = order.id
                        self.env['iber.marketplace.ciceksepeti.order.line'].create(ld[2])
                    created += 1

            # Sayfalama — sonraki sayfa yoksa çık
            total_pages = data.get('totalPages') or data.get('pageCount') or 1
            page += 1
            if page >= total_pages:
                break

        self.config_id.write({'last_order_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d yeni sipariş oluşturuldu, %d sipariş güncellendi. Toplam: %d'
        ) % (created, updated, created + updated)

    # ------------------------------------------------------------------
    # Stok senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_inventory(self):
        listings = self.env['iber.marketplace.ciceksepeti.listing'].search([
            ('config_id', '=', self.config_id.id),
            ('active', '=', True),
        ])
        if not listings:
            self.result_message = _('Aktif ürün listesi bulunamadı.')
            return
        listings.action_push_inventory()
        self.config_id.write({'last_inventory_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d ürün için stok/fiyat Çiçeksepeti\'ne gönderildi.') % len(listings)

    # ------------------------------------------------------------------
    # Alan eşleştirme yardımcıları
    # ------------------------------------------------------------------

    def _map_order_vals(self, o):
        """Çiçeksepeti sipariş dict'ini Odoo alan değerlerine çevirir."""
        ship = o.get('shippingAddress') or {}
        customer_name = (
            o.get('customerName')
            or ship.get('fullName')
            or ship.get('name')
            or ''
        )
        ship_address = ship.get('address') or ship.get('fullAddress') or ''
        ship_city = ship.get('city') or ''
        ship_district = ship.get('district') or ''

        order_date = self._iso_to_datetime(
            o.get('orderDate') or o.get('createdDate'))

        lines = []
        for item in (o.get('items') or []):
            lines.append((0, 0, self._map_line_vals(item)))

        return {
            'order_code': o.get('orderCode') or o.get('order_code') or '',
            'order_date': order_date,
            'status': o.get('status') or False,
            'customer_name': customer_name,
            'customer_email': o.get('customerEmail') or '',
            'ship_address': ship_address,
            'ship_city': ship_city,
            'ship_district': ship_district,
            'total_price': float(o.get('totalPrice') or 0.0),
            'cargo_tracking_number': o.get('cargoTrackingNumber') or '',
            'line_ids': lines,
        }

    def _map_line_vals(self, item):
        """Çiçeksepeti sipariş kalemi dict'ini Odoo alan değerlerine çevirir."""
        return {
            'order_item_code': item.get('orderItemCode') or item.get('id') or '',
            'stock_code': item.get('stockCode') or item.get('sku') or '',
            'product_name': item.get('productName') or item.get('name') or '',
            'quantity': float(item.get('quantity') or 0),
            'price': float(item.get('price') or 0.0),
            'status': item.get('status') or False,
            'cargo_company': item.get('cargoCompany') or '',
            'cargo_tracking_number': item.get('trackingNumber') or '',
        }

    @staticmethod
    def _iso_to_datetime(s):
        """ISO8601 string'ini Odoo datetime string'ine çevirir."""
        if not s:
            return False
        try:
            # Z suffix veya +00:00 ile gelebilir
            s = str(s).replace('Z', '+00:00')
            from datetime import timezone
            dt = datetime.fromisoformat(s)
            # UTC'ye çevir
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, AttributeError):
            return False
