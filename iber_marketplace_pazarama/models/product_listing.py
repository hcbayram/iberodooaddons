from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberPazaramaListing(models.Model):
    _name = 'iber.marketplace.pazarama.listing'
    _description = 'Pazarama Ürün Listesi'
    _rec_name = 'stock_code'

    config_id = fields.Many2one(
        'iber.marketplace.pazarama.config', required=True,
        ondelete='cascade', string='Bağlantı')
    company_id = fields.Many2one(
        related='config_id.company_id', store=True, string='Şirket')

    product_id = fields.Many2one(
        'product.product', required=True, string='Odoo Ürünü')
    stock_code = fields.Char(required=True, index=True, string='Stok Kodu')
    active = fields.Boolean(default=True)

    # Pazarama'dan gelen bilgiler
    pz_stock = fields.Integer(readonly=True, string='Pazarama Stoku')
    pz_price = fields.Float(readonly=True, string='Pazarama Fiyatı')
    last_push = fields.Datetime(readonly=True, string='Son Stok Gönderimi')

    # Odoo'dan hesaplanan değerler
    odoo_qty = fields.Float(compute='_compute_odoo_qty', string='Odoo Stoku')
    sale_price = fields.Float(compute='_compute_sale_price', string='Satış Fiyatı')

    # ------------------------------------------------------------------
    # Hesaplanan alanlar
    # ------------------------------------------------------------------

    @api.depends('product_id', 'product_id.qty_available')
    def _compute_odoo_qty(self):
        for rec in self:
            rec.odoo_qty = rec.product_id.qty_available if rec.product_id else 0.0

    @api.depends('product_id', 'product_id.lst_price')
    def _compute_sale_price(self):
        for rec in self:
            rec.sale_price = rec.product_id.lst_price if rec.product_id else 0.0

    # ------------------------------------------------------------------
    # Aksiyonlar
    # ------------------------------------------------------------------

    def action_push_inventory(self):
        """Seçili listingları Pazarama'ya stok ve fiyat olarak gönder."""
        configs = self.mapped('config_id')
        for cfg in configs:
            group_listings = self.filtered(lambda l: l.config_id == cfg)
            client = cfg._get_client()

            stock_items = []
            price_items = []
            for listing in group_listings:
                stock_items.append({
                    'stockCode': listing.stock_code,
                    'quantity': int(listing.odoo_qty),
                })
                price_items.append({
                    'stockCode': listing.stock_code,
                    'salePrice': listing.sale_price,
                    'listPrice': listing.sale_price,
                })

            errors = []

            # Stok güncellemesi — 100'er parça
            for i in range(0, len(stock_items), 100):
                batch = stock_items[i:i + 100]
                try:
                    client.update_stock(batch)
                except Exception as exc:
                    errors.append(_('Stok hatası: %s') % exc)

            # Fiyat güncellemesi — 100'er parça
            for i in range(0, len(price_items), 100):
                batch = price_items[i:i + 100]
                try:
                    client.update_price(batch)
                except Exception as exc:
                    errors.append(_('Fiyat hatası: %s') % exc)

            if errors:
                raise UserError(
                    _('Güncelleme sırasında hata oluştu:\n%s') % '\n'.join(errors))

        now = fields.Datetime.now()
        self.write({'last_push': now})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _(
                    "%d ürün için stok/fiyat Pazarama'ya gönderildi."
                ) % len(self),
                'type': 'success',
                'sticky': False,
            },
        }
