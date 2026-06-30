from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberHepsiburadaSyncWizard(models.TransientModel):
    _name = 'iber.marketplace.hepsiburada.sync.wizard'
    _description = 'Hepsiburada Senkronizasyon Sihirbazı'

    config_id = fields.Many2one(
        'iber.marketplace.hepsiburada.config', required=True, string='Bağlantı')
    sync_type = fields.Selection([
        ('orders', 'Siparişler'),
        ('inventory', 'Stok / Fiyat'),
    ], required=True, default='orders', string='Senkronizasyon Türü')

    # Sipariş seçenekleri
    order_status_filter = fields.Char(
        string='Durum Filtresi (boş=hepsi)',
        help='Örn: New — tek bir Hepsiburada durum değeri')
    order_days_back = fields.Integer(
        default=7, string='Son N Gün',
        help='Kaç günlük siparişlerin çekileceği')

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

        # Hepsiburada ISO8601 format kullanır
        begin_date = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_date = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        filters = {
            'beginDate': begin_date,
            'endDate': end_date,
        }
        if self.order_status_filter and self.order_status_filter.strip():
            filters['status'] = self.order_status_filter.strip()

        created = updated = offset = 0
        limit = 100
        Order = self.env['iber.marketplace.hepsiburada.order']

        while True:
            try:
                data = client.get_orders(offset=offset, limit=limit, **filters)
            except Exception as exc:
                raise UserError(_('Hepsiburada sipariş çekme hatası: %s') % exc)

            # Hepsiburada yanıt yapısı: {'data': [...]} veya doğrudan liste
            if isinstance(data, dict):
                content = data.get('data') or data.get('orders') or []
            elif isinstance(data, list):
                content = data
            else:
                content = []

            if not content:
                break

            for raw in content:
                hb_order_id = str(raw.get('id') or raw.get('orderId') or '')
                if not hb_order_id:
                    continue

                existing = Order.search([
                    ('config_id', '=', self.config_id.id),
                    ('hb_order_id', '=', hb_order_id),
                ], limit=1)

                vals = self._map_order_vals(raw)
                line_data = vals.pop('line_ids', [])

                if existing:
                    existing.write(vals)
                    existing.line_ids.unlink()
                    for ld in line_data:
                        ld[2]['order_id'] = existing.id
                        self.env['iber.marketplace.hepsiburada.order.line'].create(ld[2])
                    updated += 1
                else:
                    vals['config_id'] = self.config_id.id
                    order = Order.create(vals)
                    for ld in line_data:
                        ld[2]['order_id'] = order.id
                        self.env['iber.marketplace.hepsiburada.order.line'].create(ld[2])
                    created += 1

            # Sayfalama: dönen kayıt sayısı limit'ten az ise son sayfadayız
            if len(content) < limit:
                break
            offset += limit

        self.config_id.write({'last_order_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d yeni sipariş oluşturuldu, %d sipariş güncellendi. Toplam: %d'
        ) % (created, updated, created + updated)

    # ------------------------------------------------------------------
    # Stok senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_inventory(self):
        listings = self.env['iber.marketplace.hepsiburada.listing'].search([
            ('config_id', '=', self.config_id.id),
            ('active', '=', True),
        ])
        if not listings:
            self.result_message = _('Aktif ürün listesi bulunamadı.')
            return
        listings.action_push_inventory()
        self.config_id.write({'last_inventory_sync': fields.Datetime.now()})
        self.result_message = _(
            "%d ürün için stok/fiyat Hepsiburada'ya gönderildi.") % len(listings)

    # ------------------------------------------------------------------
    # Alan eşleştirme yardımcıları
    # ------------------------------------------------------------------

    def _map_order_vals(self, o):
        """Hepsiburada sipariş dict'ini Odoo alan değerlerine çevirir."""
        # Müşteri adı
        customer = o.get('customer') or {}
        first = customer.get('firstName') or ''
        last = customer.get('lastName') or ''
        customer_name = f'{first} {last}'.strip() or customer.get('name') or ''

        # Teslimat adresi
        ship_addr = o.get('shippingAddress') or {}
        ship_address = ship_addr.get('address') or ''
        ship_city = ship_addr.get('city') or ''
        ship_district = ship_addr.get('district') or ''

        # Fatura adresi
        inv_addr = o.get('invoiceAddress') or {}
        invoice_address = inv_addr.get('address') or ''
        invoice_city = inv_addr.get('city') or ''

        # Tarih: ISO string → Odoo datetime
        order_date = self._iso_to_datetime(o.get('orderDate'))

        # Satırlar
        lines = []
        for line in (o.get('lineItems') or []):
            lines.append((0, 0, self._map_line_vals(line)))

        return {
            'hb_order_id': str(o.get('id') or o.get('orderId') or ''),
            'order_number': str(o.get('orderNumber') or ''),
            'order_date': order_date,
            'status': o.get('status') or False,
            'customer_name': customer_name,
            'customer_email': customer.get('email') or '',
            'ship_address': ship_address,
            'ship_city': ship_city,
            'ship_district': ship_district,
            'invoice_address': invoice_address,
            'invoice_city': invoice_city,
            'total_price': float(o.get('totalPrice') or 0.0),
            'cargo_company': o.get('cargoCompany') or '',
            'cargo_tracking_number': o.get('cargoTrackingNumber') or '',
            'line_ids': lines,
        }

    def _map_line_vals(self, line):
        """Hepsiburada sipariş satır dict'ini Odoo alan değerlerine çevirir."""
        return {
            'hb_line_id': str(line.get('id') or ''),
            'hepsiburada_sku': line.get('hepsiburadaSku') or '',
            'merchant_sku': line.get('merchantSku') or '',
            'product_name': line.get('productName') or '',
            'quantity': float(line.get('quantity') or 0),
            'price': float(line.get('price') or 0.0),
            'status': line.get('status') or False,
            'cargo_company': line.get('cargoCompany') or '',
            'cargo_tracking_number': line.get('cargoTrackingNumber') or '',
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
