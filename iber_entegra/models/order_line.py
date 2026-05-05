from odoo import models, fields, api


class IberEntegraOrderLine(models.Model):
    _name = 'iber.entegra.order.line'
    _description = 'Entegra Sipariş Kalemi'
    _rec_name = 'product_code'

    order_id = fields.Many2one(
        'iber.entegra.order', required=True, ondelete='cascade')

    product_code = fields.Char(string='Ürün Kodu', readonly=True)
    product_name = fields.Char(string='Ürün Adı', readonly=True)
    quantity = fields.Integer(string='Miktar', readonly=True)
    price = fields.Float(string='Birim Fiyat', readonly=True)
    first_price = fields.Float(string='KDV Hariç Fiyat', readonly=True)

    subtotal = fields.Float(
        string='Toplam', compute='_compute_subtotal', store=True)

    product_mapping_id = fields.Many2one(
        'iber.entegra.product.mapping',
        string='Odoo Ürünü',
        compute='_compute_product_mapping',
        store=True,
    )

    @api.depends('price', 'quantity')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.price * rec.quantity

    @api.depends('product_code', 'order_id.config_id')
    def _compute_product_mapping(self):
        for rec in self:
            if rec.product_code and rec.order_id.config_id:
                rec.product_mapping_id = self.env['iber.entegra.product.mapping'].search([
                    ('config_id', '=', rec.order_id.config_id.id),
                    ('entegra_product_code', '=', rec.product_code),
                ], limit=1)
            else:
                rec.product_mapping_id = False
