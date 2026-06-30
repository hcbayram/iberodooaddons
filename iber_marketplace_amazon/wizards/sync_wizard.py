from datetime import datetime, timedelta, timezone

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberAmazonSyncWizard(models.TransientModel):
    _name = 'iber.marketplace.amazon.sync.wizard'
    _description = 'Amazon TR Senkronizasyon Sihirbazı'

    config_id = fields.Many2one(
        'iber.marketplace.amazon.config', required=True, string='Bağlantı')
    sync_type = fields.Selection([
        ('orders', 'Siparişler'),
        ('inventory', 'Stok / Fiyat'),
    ], required=True, default='orders', string='Senkronizasyon Türü')

    # Sipariş seçenekleri
    order_days_back = fields.Integer(
        default=7, string='Son N Gün',
        help='Kaç günlük siparişlerin çekileceği')
    include_all_statuses = fields.Boolean(
        default=False, string='Tüm Durumlar',
        help='İşaretlenmezse yalnızca Unshipped ve PartiallyShipped çekilir')

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

        created_after = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime('%Y-%m-%dT%H:%M:%SZ')

        statuses = None
        if not self.include_all_statuses:
            statuses = ['Unshipped', 'PartiallyShipped', 'Pending']

        created = updated = 0
        Order = self.env['iber.marketplace.amazon.order']
        next_token = None

        while True:
            try:
                payload = client.get_orders(
                    created_after=created_after if not next_token else None,
                    order_statuses=statuses if not next_token else None,
                    next_token=next_token,
                )
            except Exception as exc:
                raise UserError(_('Amazon sipariş çekme hatası: %s') % exc)

            orders = payload.get('Orders') or []
            for raw in orders:
                amazon_order_id = raw.get('AmazonOrderId', '')
                if not amazon_order_id:
                    continue

                # Sipariş kalemlerini çek
                try:
                    items_payload = client.get_order_items(amazon_order_id)
                    raw_items = items_payload.get('OrderItems') or []
                except Exception:
                    raw_items = []

                existing = Order.search([
                    ('config_id', '=', self.config_id.id),
                    ('amazon_order_id', '=', amazon_order_id),
                ], limit=1)

                vals = self._map_order_vals(raw)
                line_data = [self._map_line_vals(it) for it in raw_items]

                if existing:
                    existing.write(vals)
                    existing.line_ids.unlink()
                    for ld in line_data:
                        ld['order_id'] = existing.id
                        self.env['iber.marketplace.amazon.order.line'].create(ld)
                    updated += 1
                else:
                    vals['config_id'] = self.config_id.id
                    order = Order.create(vals)
                    for ld in line_data:
                        ld['order_id'] = order.id
                        self.env['iber.marketplace.amazon.order.line'].create(ld)
                    created += 1

            next_token = payload.get('NextToken')
            if not next_token:
                break

        self.config_id.write({'last_order_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d yeni sipariş oluşturuldu, %d sipariş güncellendi. Toplam: %d'
        ) % (created, updated, created + updated)

    # ------------------------------------------------------------------
    # Stok senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_inventory(self):
        listings = self.env['iber.marketplace.amazon.listing'].search([
            ('config_id', '=', self.config_id.id),
            ('active', '=', True),
        ])
        if not listings:
            self.result_message = _('Aktif ürün listesi bulunamadı.')
            return
        listings.action_push_inventory()
        self.config_id.write({'last_inventory_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d ürün için stok/fiyat Amazon\'a gönderildi.') % len(listings)

    # ------------------------------------------------------------------
    # Alan eşleştirme yardımcıları
    # ------------------------------------------------------------------

    def _map_order_vals(self, o):
        addr = o.get('ShippingAddress') or {}
        buyer = o.get('BuyerInfo') or {}

        total = o.get('OrderTotal') or {}
        order_total = float(total.get('Amount') or 0.0)
        currency_code = total.get('CurrencyCode') or 'TRY'

        return {
            'amazon_order_id': o.get('AmazonOrderId', ''),
            'purchase_date': self._iso_to_datetime(o.get('PurchaseDate')),
            'status': o.get('OrderStatus') or False,
            'fulfillment_channel': o.get('FulfillmentChannel') or False,
            'buyer_name': buyer.get('BuyerName') or '',
            'buyer_email': buyer.get('BuyerEmail') or '',
            'ship_name': addr.get('Name') or '',
            'ship_address_line1': addr.get('AddressLine1') or '',
            'ship_address_line2': addr.get('AddressLine2') or '',
            'ship_city': addr.get('City') or '',
            'ship_state': addr.get('StateOrRegion') or '',
            'ship_postal_code': addr.get('PostalCode') or '',
            'ship_country_code': addr.get('CountryCode') or '',
            'order_total': order_total,
            'currency_code': currency_code,
        }

    def _map_line_vals(self, item):
        item_price_dict = item.get('ItemPrice') or {}
        item_tax_dict = item.get('ItemTax') or {}
        return {
            'order_item_id': item.get('OrderItemId') or '',
            'asin': item.get('ASIN') or '',
            'seller_sku': item.get('SellerSKU') or '',
            'title': item.get('Title') or '',
            'quantity_ordered': float(item.get('QuantityOrdered') or 0),
            'quantity_shipped': float(item.get('QuantityShipped') or 0),
            'item_price': float(item_price_dict.get('Amount') or 0.0),
            'item_tax': float(item_tax_dict.get('Amount') or 0.0),
            'currency_code': item_price_dict.get('CurrencyCode') or 'TRY',
        }

    @staticmethod
    def _iso_to_datetime(s):
        if not s:
            return False
        try:
            s = str(s).replace('Z', '+00:00')
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, AttributeError):
            return False
