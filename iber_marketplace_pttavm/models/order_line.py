from odoo import models, fields
from ..core.pttavm_const import ORDER_STATUSES


class IberPttavmOrderLine(models.Model):
    _name = 'iber.marketplace.pttavm.order.line'
    _description = 'PttAVM Sipariş Kalemi'
    _rec_name = 'product_name'

    order_id = fields.Many2one(
        'iber.marketplace.pttavm.order', required=True,
        ondelete='cascade', string='Sipariş')
    config_id = fields.Many2one(
        related='order_id.config_id', store=True, string='Bağlantı')
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, string='Şirket')

    # PttAVM satır alanları
    pttavm_line_id = fields.Char(readonly=True, string='PttAVM Satır ID')
    barcode = fields.Char(readonly=True, string='Barkod')
    product_name = fields.Char(readonly=True, string='Ürün Adı')
    quantity = fields.Float(readonly=True, string='Miktar')
    price = fields.Float(readonly=True, string='Birim Fiyat')
    status = fields.Selection(
        selection=ORDER_STATUSES,
        readonly=True, string='Durum')

    # Odoo ürün eşleşmesi
    product_id = fields.Many2one('product.product', string='Odoo Ürünü')
