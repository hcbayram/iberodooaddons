from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberN11SyncWizard(models.TransientModel):
    _name = 'iber.marketplace.n11.sync.wizard'
    _description = 'N11 Senkronizasyon Sihirbazı'

    config_id = fields.Many2one(
        'iber.marketplace.n11.config', required=True, string='Bağlantı')
    sync_type = fields.Selection([
        ('orders', 'Siparişler'),
        ('inventory', 'Stok'),
    ], required=True, default='orders', string='Senkronizasyon Türü')

    # Sipariş seçenekleri
    order_days_back = fields.Integer(
        default=7, string='Son N Gün',
        help='Kaç günlük siparişlerin çekileceği')
    order_status_filter = fields.Char(
        string='Durum Filtresi',
        help='N11 durum kodu, örn: New')

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

        # N11 DD/MM/YYYY tarih formatı
        start_date = start_dt.strftime('%d/%m/%Y')
        end_date = now_dt.strftime('%d/%m/%Y')

        status_filter = (self.order_status_filter or '').strip() or None

        created = updated = 0
        page = 0
        Order = self.env['iber.marketplace.n11.order']

        while True:
            try:
                orders = client.get_orders(
                    page=page,
                    page_size=100,
                    status=status_filter,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as exc:
                raise UserError(_('N11 sipariş çekme hatası: %s') % exc)

            if not orders:
                break

            for raw in orders:
                n11_order_id = str(raw.get('id') or '').strip()
                if not n11_order_id:
                    continue

                existing = Order.search([
                    ('config_id', '=', self.config_id.id),
                    ('n11_order_id', '=', n11_order_id),
                ], limit=1)

                vals = self._map_order_vals(raw)
                line_data = vals.pop('line_ids', [])

                if existing:
                    existing.write(vals)
                    existing.line_ids.unlink()
                    for ld in line_data:
                        ld[2]['order_id'] = existing.id
                        self.env['iber.marketplace.n11.order.line'].create(ld[2])
                    updated += 1
                else:
                    vals['config_id'] = self.config_id.id
                    order = Order.create(vals)
                    for ld in line_data:
                        ld[2]['order_id'] = order.id
                        self.env['iber.marketplace.n11.order.line'].create(ld[2])
                    created += 1

            # N11 sayfalama: tam sayfa geldiyse devam et
            if len(orders) < 100:
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
        listings = self.env['iber.marketplace.n11.listing'].search([
            ('config_id', '=', self.config_id.id),
            ('active', '=', True),
        ])
        if not listings:
            self.result_message = _('Aktif ürün listesi bulunamadı.')
            return
        listings.action_push_inventory()
        self.config_id.write({'last_inventory_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d ürün için stok N11\'e gönderildi.') % len(listings)

    # ------------------------------------------------------------------
    # Alan eşleştirme yardımcıları
    # ------------------------------------------------------------------

    def _map_order_vals(self, o):
        """N11 sipariş dict'ini Odoo alan değerlerine çevirir."""
        n11_order_id = str(o.get('id') or '')
        order_number = str(o.get('orderNumber') or n11_order_id)

        # Alıcı bilgileri
        buyer = o.get('buyer') or {}
        if isinstance(buyer, dict):
            customer_name = buyer.get('fullName') or ''
            customer_email = buyer.get('email') or ''
        else:
            customer_name = ''
            customer_email = ''

        # Teslimat adresi
        ship_addr_raw = o.get('shippingAddress') or {}
        if isinstance(ship_addr_raw, dict):
            ship_address = ship_addr_raw.get('address') or ''
            ship_city = ship_addr_raw.get('city') or ''
            ship_district = (
                ship_addr_raw.get('district')
                or ship_addr_raw.get('town')
                or ''
            )
        else:
            ship_address = ship_city = ship_district = ''

        # Toplam tutar
        try:
            total_price = float(o.get('totalAmount') or 0.0)
        except (TypeError, ValueError):
            total_price = 0.0

        # Kargo bilgisi
        shipment_info = o.get('shipmentInfo') or {}
        if isinstance(shipment_info, dict):
            cargo_company = shipment_info.get('shipmentCompany') or ''
            cargo_tracking = shipment_info.get('trackingNumber') or ''
        else:
            cargo_company = cargo_tracking = ''

        # Sipariş tarihi
        order_date = self._n11_date_to_odoo(o.get('createDate'))

        # Durum
        status = o.get('status') or False

        # Satırlar
        item_list = o.get('itemList') or {}
        if isinstance(item_list, dict):
            items_raw = item_list.get('item') or []
        else:
            items_raw = []
        if isinstance(items_raw, dict):
            items_raw = [items_raw]

        lines = [(0, 0, self._map_line_vals(item)) for item in items_raw]

        return {
            'n11_order_id': n11_order_id,
            'order_number': order_number,
            'order_date': order_date,
            'status': status,
            'customer_name': customer_name,
            'customer_email': customer_email,
            'ship_address': ship_address,
            'ship_city': ship_city,
            'ship_district': ship_district,
            'total_price': total_price,
            'cargo_company': cargo_company,
            'cargo_tracking_number': cargo_tracking,
            'line_ids': lines,
        }

    def _map_line_vals(self, item):
        """N11 sipariş kalemi dict'ini Odoo alan değerlerine çevirir."""
        try:
            quantity = float(item.get('quantity') or 0)
        except (TypeError, ValueError):
            quantity = 0.0
        try:
            price = float(item.get('unitPrice') or 0.0)
        except (TypeError, ValueError):
            price = 0.0

        return {
            'n11_item_id': str(item.get('id') or ''),
            'seller_stock_code': item.get('sellerStockCode') or '',
            'product_name': item.get('productName') or '',
            'quantity': quantity,
            'price': price,
            'status': item.get('status') or False,
        }

    @staticmethod
    def _n11_date_to_odoo(s):
        """
        N11 tarih string'ini Odoo datetime string'ine çevirir.
        Desteklenen formatlar: DD/MM/YYYY veya DD/MM/YYYY HH:MM:SS
        None/boş → False
        """
        if not s:
            return False
        s = str(s).strip()
        for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
        return False
