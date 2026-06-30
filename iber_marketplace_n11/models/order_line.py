from odoo import models, fields

from ..core.n11_const import ORDER_STATUSES


class IberN11OrderLine(models.Model):
    _name = 'iber.marketplace.n11.order.line'
    _description = 'N11 Sipariş Kalemi'
    _rec_name = 'product_name'

    order_id = fields.Many2one(
        'iber.marketplace.n11.order', required=True,
        ondelete='cascade', string='Sipariş')
    config_id = fields.Many2one(
        related='order_id.config_id', store=True, string='Bağlantı')
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, string='Şirket')

    # N11 satır alanları
    n11_item_id = fields.Char(readonly=True, string='N11 Kalem ID')
    seller_stock_code = fields.Char(readonly=True, string='Satıcı SKU')
    product_name = fields.Char(readonly=True, string='Ürün Adı')
    quantity = fields.Float(readonly=True, string='Miktar')
    price = fields.Float(readonly=True, string='Birim Fiyat')
    status = fields.Selection(
        selection=ORDER_STATUSES,
        readonly=True, string='Durum')

    # Odoo ürün eşleşmesi
    product_id = fields.Many2one('product.product', string='Odoo Ürünü')
