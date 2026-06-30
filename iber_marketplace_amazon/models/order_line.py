from odoo import models, fields
from ..core.amazon_const import ORDER_STATUSES


class IberAmazonOrderLine(models.Model):
    _name = 'iber.marketplace.amazon.order.line'
    _description = 'Amazon TR Sipariş Kalemi'
    _rec_name = 'title'

    order_id = fields.Many2one(
        'iber.marketplace.amazon.order', required=True,
        ondelete='cascade', string='Sipariş')
    config_id = fields.Many2one(
        related='order_id.config_id', store=True, string='Bağlantı')
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, string='Şirket')

    # Amazon kalem alanları
    order_item_id = fields.Char(readonly=True, string='Kalem ID')
    asin = fields.Char(readonly=True, string='ASIN', index=True)
    seller_sku = fields.Char(readonly=True, string='Satıcı SKU', index=True)
    title = fields.Char(readonly=True, string='Ürün Adı')
    quantity_ordered = fields.Float(readonly=True, string='Sipariş Miktarı')
    quantity_shipped = fields.Float(readonly=True, string='Kargolanan Miktar')
    item_price = fields.Float(readonly=True, string='Birim Fiyat')
    item_tax = fields.Float(readonly=True, string='KDV')
    currency_code = fields.Char(readonly=True, string='Para Birimi', default='TRY')
    status = fields.Selection(
        selection=ORDER_STATUSES, readonly=True, string='Durum')

    # Odoo ürün eşleşmesi
    product_id = fields.Many2one('product.product', string='Odoo Ürünü')
