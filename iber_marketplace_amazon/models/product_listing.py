from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberAmazonListing(models.Model):
    _name = 'iber.marketplace.amazon.listing'
    _description = 'Amazon TR Ürün Listesi'
    _rec_name = 'seller_sku'

    config_id = fields.Many2one(
        'iber.marketplace.amazon.config', required=True,
        ondelete='cascade', string='Bağlantı')
    company_id = fields.Many2one(
        related='config_id.company_id', store=True, string='Şirket')

    product_id = fields.Many2one(
        'product.product', required=True, string='Odoo Ürünü')
    seller_sku = fields.Char(
        required=True, index=True, string='Satıcı SKU')
    asin = fields.Char(string='ASIN', readonly=True)
    active = fields.Boolean(default=True)

    # Amazon'dan gelen bilgiler
    amz_quantity = fields.Integer(readonly=True, string='Amazon Stoku')
    amz_price = fields.Float(readonly=True, string='Amazon Fiyatı')
    last_push = fields.Datetime(readonly=True, string='Son Gönderim')

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
        """Seçili listing'leri Amazon'a stok ve fiyat olarak gönder (Feeds API)."""
        configs = self.mapped('config_id')
        errors = []

        for cfg in configs:
            group_listings = self.filtered(lambda l: l.config_id == cfg)
            client = cfg._get_client()

            inventory_items = [
                {'sku': l.seller_sku, 'quantity': int(l.odoo_qty)}
                for l in group_listings
            ]
            price_items = [
                {'sku': l.seller_sku, 'price': l.sale_price, 'currency': 'TRY'}
                for l in group_listings
            ]

            # 100'er parça — Feed API büyük XML'leri kaldırır ama sınır koyuyoruz
            for i in range(0, len(inventory_items), 100):
                try:
                    client.update_inventory(inventory_items[i:i + 100])
                except Exception as exc:
                    errors.append(f'Stok: {exc}')

            for i in range(0, len(price_items), 100):
                try:
                    client.update_price(price_items[i:i + 100])
                except Exception as exc:
                    errors.append(f'Fiyat: {exc}')

        if errors:
            raise UserError(
                _('Stok/fiyat güncellemesi sırasında hata:\n%s') % '\n'.join(errors))

        self.write({'last_push': fields.Datetime.now()})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('%d ürün için stok/fiyat Amazon\'a gönderildi.') % len(self),
                'type': 'success',
                'sticky': False,
            },
        }
