from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberCiceksepetiListing(models.Model):
    _name = 'iber.marketplace.ciceksepeti.listing'
    _description = 'Çiçeksepeti Ürün Listesi'
    _rec_name = 'stock_code'

    config_id = fields.Many2one(
        'iber.marketplace.ciceksepeti.config', required=True,
        ondelete='cascade', string='Bağlantı')
    company_id = fields.Many2one(
        related='config_id.company_id', store=True, string='Şirket')

    product_id = fields.Many2one(
        'product.product', required=True, string='Odoo Ürünü')
    stock_code = fields.Char(
        required=True, index=True, string='Stok Kodu')
    active = fields.Boolean(default=True)

    # Çiçeksepeti'nden gelen bilgiler
    cs_stock = fields.Integer(readonly=True, string='CS Stoku')
    cs_price = fields.Float(readonly=True, string='CS Fiyatı')
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
        """Seçili listingları Çiçeksepeti'ne stok ve fiyat olarak gönder."""
        configs = self.mapped('config_id')
        errors = []

        for cfg in configs:
            group_listings = self.filtered(lambda l: l.config_id == cfg)
            client = cfg._get_client()

            stock_items = [
                {'stockCode': l.stock_code, 'stock': int(l.odoo_qty)}
                for l in group_listings
            ]
            price_items = [
                {
                    'stockCode': l.stock_code,
                    'salesPrice': l.sale_price,
                    'listPrice': l.sale_price,
                }
                for l in group_listings
            ]

            # Batch işleme (100'er parça)
            for i in range(0, len(stock_items), 100):
                try:
                    client.update_stock(stock_items[i:i + 100])
                except Exception as exc:
                    errors.append(str(exc))

            for i in range(0, len(price_items), 100):
                try:
                    client.update_price(price_items[i:i + 100])
                except Exception as exc:
                    errors.append(str(exc))

        if errors:
            raise UserError(
                _('Stok/fiyat güncellemesi sırasında hata oluştu:\n%s') % '\n'.join(errors))

        self.write({'last_push': fields.Datetime.now()})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _(
                    '%d ürün için stok/fiyat Çiçeksepeti\'ne gönderildi.') % len(self),
                'type': 'success',
                'sticky': False,
            },
        }
