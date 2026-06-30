import json
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberTrendyolSyncWizard(models.TransientModel):
    _name = 'iber.marketplace.trendyol.sync.wizard'
    _description = 'Trendyol Senkronizasyon Sihirbazı'

    config_id = fields.Many2one(
        'iber.marketplace.trendyol.config', required=True, string='Bağlantı')
    sync_type = fields.Selection([
        ('orders', 'Siparişler'),
        ('inventory', 'Stok / Fiyat'),
    ], required=True, default='orders', string='Senkronizasyon Türü')

    # Sipariş seçenekleri
    order_status_filter = fields.Char(
        string='Durum Filtresi (boş=hepsi)',
        help='Örn: Created,Picking — birden fazla için virgülle ayırın')
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
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(now_dt.timestamp() * 1000)

        filters = {
            'startDate': start_ms,
            'endDate': end_ms,
            'orderByField': 'CreatedDate',
            'orderByDirection': 'DESC',
        }
        if self.order_status_filter and self.order_status_filter.strip():
            filters['status'] = self.order_status_filter.strip()

        created = updated = page = 0
        Order = self.env['iber.marketplace.trendyol.order']

        while True:
            try:
                data = client.get_orders(page=page, size=200, **filters)
            except Exception as exc:
                raise UserError(_('Trendyol sipariş çekme hatası: %s') % exc)

            content = data.get('content') or []
            if not content:
                break

            for raw in content:
                trendyol_id = raw.get('id') or raw.get('orderId') or 0
                if not trendyol_id:
                    continue
                try:
                    trendyol_id = int(trendyol_id)
                except (TypeError, ValueError):
                    continue

                existing = Order.search([
                    ('config_id', '=', self.config_id.id),
                    ('trendyol_id', '=', trendyol_id),
                ], limit=1)

                vals = self._map_order_vals(raw)
                line_data = vals.pop('line_ids', [])

                if existing:
                    existing.write(vals)
                    existing.line_ids.unlink()
                    for ld in line_data:
                        ld[2]['order_id'] = existing.id
                        self.env['iber.marketplace.trendyol.order.line'].create(ld[2])
                    updated += 1
                else:
                    vals['config_id'] = self.config_id.id
                    order = Order.create(vals)
                    for ld in line_data:
                        ld[2]['order_id'] = order.id
                        self.env['iber.marketplace.trendyol.order.line'].create(ld[2])
                    created += 1

            # Trendyol sayfalama bilgisi
            total_pages = data.get('totalPages') or 1
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
        listings = self.env['iber.marketplace.trendyol.listing'].search([
            ('config_id', '=', self.config_id.id),
            ('active', '=', True),
        ])
        if not listings:
            self.result_message = _('Aktif ürün listesi bulunamadı.')
            return
        listings.action_push_inventory()
        self.config_id.write({'last_inventory_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d ürün için stok/fiyat Trendyol\'a gönderildi.') % len(listings)

    # ------------------------------------------------------------------
    # Alan eşleştirme yardımcıları
    # ------------------------------------------------------------------

    def _map_order_vals(self, o):
        """Trendyol sipariş dict'ini Odoo alan değerlerine çevirir."""
        # Müşteri adı
        customer_name = o.get('customerFirstLastName') or ''
        if not customer_name:
            ship = o.get('shipmentAddress') or {}
            first = ship.get('firstName') or ''
            last = ship.get('lastName') or ''
            customer_name = f'{first} {last}'.strip()

        # Fatura adresi
        inv_addr = o.get('invoiceAddress') or {}
        invoice_address = inv_addr.get('address1') or inv_addr.get('address') or ''
        invoice_city = inv_addr.get('city') or ''

        # Teslimat adresi
        ship_addr = o.get('shipmentAddress') or {}
        ship_address = ship_addr.get('address1') or ship_addr.get('address') or ''
        ship_city = ship_addr.get('city') or ''

        # Tarih: epoch ms → Odoo datetime
        order_date = self._ms_to_datetime(o.get('orderDate'))

        # Satırlar
        lines = []
        for line in (o.get('lines') or []):
            lines.append((0, 0, self._map_line_vals(line)))

        return {
            'trendyol_id': o.get('id') or o.get('orderId') or 0,
            'order_number': str(o.get('orderNumber') or ''),
            'gross_amount': float(o.get('grossAmount') or 0.0),
            'total_discount': float(o.get('totalDiscount') or 0.0),
            'total_price': float(o.get('totalPrice') or 0.0),
            'order_date': order_date,
            'status': o.get('status') or False,
            'customer_name': customer_name,
            'customer_email': o.get('customerEmail') or '',
            'invoice_address': invoice_address,
            'invoice_city': invoice_city,
            'ship_address': ship_address,
            'ship_city': ship_city,
            'cargo_tracking_number': o.get('cargoTrackingNumber') or '',
            'cargo_provider': o.get('cargoProviderName') or '',
            'cargo_sender_number': o.get('cargoSenderNumber') or '',
            'shipment_package_id': o.get('shipmentPackageId') or 0,
            'line_ids': lines,
        }

    def _map_line_vals(self, line):
        """Trendyol sipariş satır dict'ini Odoo alan değerlerine çevirir."""
        # discountDetails bir liste olabilir — JSON string'e çevir
        discount_details = line.get('discountDetails') or ''
        if isinstance(discount_details, (list, dict)):
            try:
                discount_details = json.dumps(discount_details, ensure_ascii=False)
            except Exception:
                discount_details = str(discount_details)

        return {
            'trendyol_line_id': line.get('id') or 0,
            'barcode': line.get('barcode') or '',
            'merchant_sku': line.get('merchantSku') or '',
            'product_name': line.get('productName') or '',
            'quantity': float(line.get('quantity') or 0),
            'price': float(line.get('price') or 0.0),
            'discount_details': discount_details,
            'status': line.get('status') or False,
            'cargo_provider_name': line.get('cargoProviderName') or '',
            'cargo_tracking_number': line.get('cargoTrackingNumber') or '',
        }

    @staticmethod
    def _ms_to_datetime(ms):
        """Epoch milisaniyesini Odoo datetime string'ine çevirir."""
        if not ms:
            return False
        try:
            ts = int(ms) / 1000.0
            dt = datetime.utcfromtimestamp(ts)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError, OSError):
            return False
