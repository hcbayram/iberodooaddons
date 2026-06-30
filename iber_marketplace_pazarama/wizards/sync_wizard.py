from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberPazaramaSyncWizard(models.TransientModel):
    _name = 'iber.marketplace.pazarama.sync.wizard'
    _description = 'Pazarama Senkronizasyon Sihirbazı'

    config_id = fields.Many2one(
        'iber.marketplace.pazarama.config', required=True, string='Bağlantı')
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
        help='Örn: Created — tek bir Pazarama durum değeri')

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

        # Pazarama ISO8601 format kullanır
        start_date = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_date = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        filters = {
            'startDate': start_date,
            'endDate': end_date,
        }
        if self.order_status_filter and self.order_status_filter.strip():
            filters['status'] = self.order_status_filter.strip()

        created = updated = 0
        page = 1
        page_size = 100
        Order = self.env['iber.marketplace.pazarama.order']

        while True:
            try:
                data = client.get_orders(
                    page=page, page_size=page_size, **filters)
            except Exception as exc:
                raise UserError(_('Pazarama sipariş çekme hatası: %s') % exc)

            # Pazarama yanıt yapısı: {'data': [...]} veya doğrudan liste
            if isinstance(data, dict):
                content = data.get('data') or data.get('orders') or []
            elif isinstance(data, list):
                content = data
            else:
                content = []

            if not content:
                break

            for raw in content:
                order_code = str(
                    raw.get('orderCode') or raw.get('id') or raw.get('orderId') or ''
                )
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
                        self.env['iber.marketplace.pazarama.order.line'].create(ld[2])
                    updated += 1
                else:
                    vals['config_id'] = self.config_id.id
                    order = Order.create(vals)
                    for ld in line_data:
                        ld[2]['order_id'] = order.id
                        self.env['iber.marketplace.pazarama.order.line'].create(ld[2])
                    created += 1

            # Sayfalama: dönen kayıt sayısı page_size'dan az ise son sayfadayız
            if len(content) < page_size:
                break
            page += 1

        self.config_id.write({'last_order_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d yeni sipariş oluşturuldu, %d sipariş güncellendi. Toplam: %d'
        ) % (created, updated, created + updated)

    # ------------------------------------------------------------------
    # Stok senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_inventory(self):
        listings = self.env['iber.marketplace.pazarama.listing'].search([
            ('config_id', '=', self.config_id.id),
            ('active', '=', True),
        ])
        if not listings:
            self.result_message = _('Aktif ürün listesi bulunamadı.')
            return
        listings.action_push_inventory()
        self.config_id.write({'last_inventory_sync': fields.Datetime.now()})
        self.result_message = _(
            "%d ürün için stok/fiyat Pazarama'ya gönderildi.") % len(listings)

    # ------------------------------------------------------------------
    # Alan eşleştirme yardımcıları
    # ------------------------------------------------------------------

    def _map_order_vals(self, o):
        """Pazarama sipariş dict'ini Odoo alan değerlerine çevirir."""
        # Müşteri adı — farklı alan adlarını dene
        customer_name = (
            o.get('customerName')
            or (o.get('customer') or {}).get('name')
            or ''
        )
        customer_email = (
            o.get('customerEmail')
            or (o.get('customer') or {}).get('email')
            or ''
        )

        # Teslimat adresi
        ship_addr = o.get('shippingAddress') or {}
        if isinstance(ship_addr, str):
            ship_address = ship_addr
            ship_city = ''
            ship_district = ''
        else:
            ship_address = ship_addr.get('address') or ship_addr.get('fullAddress') or ''
            ship_city = ship_addr.get('city') or ''
            ship_district = ship_addr.get('district') or ''

        # Tarih: ISO string → Odoo datetime
        order_date = self._iso_to_datetime(
            o.get('orderDate') or o.get('createdDate') or o.get('createDate')
        )

        # Satırlar — farklı alan adlarını dene
        raw_lines = o.get('lines') or o.get('orderLines') or o.get('items') or []
        lines = []
        for line in raw_lines:
            lines.append((0, 0, self._map_line_vals(line)))

        return {
            'order_code': str(
                o.get('orderCode') or o.get('id') or o.get('orderId') or ''
            ),
            'order_date': order_date,
            'status': o.get('status') or False,
            'customer_name': customer_name,
            'customer_email': customer_email,
            'ship_address': ship_address,
            'ship_city': ship_city,
            'ship_district': ship_district,
            'total_price': float(o.get('totalPrice') or o.get('totalAmount') or 0.0),
            'cargo_company': o.get('cargoCompany') or o.get('cargoProvider') or '',
            'cargo_tracking_number': (
                o.get('trackingNumber') or o.get('cargoTrackingNumber') or ''
            ),
            'line_ids': lines,
        }

    def _map_line_vals(self, line):
        """Pazarama sipariş satır dict'ini Odoo alan değerlerine çevirir."""
        return {
            'pazarama_line_id': str(line.get('id') or line.get('lineId') or ''),
            'stock_code': line.get('stockCode') or line.get('sku') or '',
            'product_name': line.get('productName') or line.get('name') or '',
            'quantity': float(line.get('quantity') or line.get('qty') or 0),
            'price': float(line.get('price') or line.get('unitPrice') or 0.0),
            'status': line.get('status') or False,
        }

    @staticmethod
    def _iso_to_datetime(iso_str):
        """ISO8601 string'i Odoo datetime string'ine çevirir."""
        if not iso_str:
            return False
        for fmt in (
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
        ):
            try:
                dt = datetime.strptime(iso_str[:26], fmt)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
        return False
