from odoo import models, fields
from ..core.pazarama_const import ORDER_STATUSES


class IberPazaramaOrderLine(models.Model):
    _name = 'iber.marketplace.pazarama.order.line'
    _description = 'Pazarama Sipariş Kalemi'
    _rec_name = 'product_name'

    order_id = fields.Many2one(
        'iber.marketplace.pazarama.order', required=True,
        ondelete='cascade', string='Sipariş')
    config_id = fields.Many2one(
        related='order_id.config_id', store=True, string='Bağlantı')
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, string='Şirket')

    # Pazarama satır alanları
    pazarama_line_id = fields.Char(readonly=True, string='Pazarama Satır ID')
    stock_code = fields.Char(readonly=True, string='Stok Kodu')
    product_name = fields.Char(readonly=True, string='Ürün Adı')
    quantity = fields.Float(readonly=True, string='Miktar')
    price = fields.Float(readonly=True, string='Birim Fiyat')
    status = fields.Selection(
        selection=ORDER_STATUSES,
        readonly=True, string='Durum')

    # Odoo ürün eşleşmesi
    product_id = fields.Many2one('product.product', string='Odoo Ürünü')
