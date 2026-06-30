from odoo import models, fields
from ..core.hepsiburada_const import ORDER_STATUSES


class IberHepsiburadaOrderLine(models.Model):
    _name = 'iber.marketplace.hepsiburada.order.line'
    _description = 'Hepsiburada Sipariş Kalemi'
    _rec_name = 'product_name'

    order_id = fields.Many2one(
        'iber.marketplace.hepsiburada.order', required=True,
        ondelete='cascade', string='Sipariş')
    config_id = fields.Many2one(
        related='order_id.config_id', store=True, string='Bağlantı')
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, string='Şirket')

    # Hepsiburada satır alanları
    hb_line_id = fields.Char(readonly=True, string='HB Satır ID')
    hepsiburada_sku = fields.Char(readonly=True, string='HB SKU')
    merchant_sku = fields.Char(readonly=True, string='Satıcı SKU')
    product_name = fields.Char(readonly=True, string='Ürün Adı')
    quantity = fields.Float(readonly=True, string='Miktar')
    price = fields.Float(readonly=True, string='Birim Fiyat')
    status = fields.Selection(
        selection=ORDER_STATUSES,
        readonly=True, string='Durum')
    cargo_company = fields.Char(readonly=True, string='Kargo Şirketi')
    cargo_tracking_number = fields.Char(readonly=True, string='Kargo Takip No')

    # Odoo ürün eşleşmesi
    product_id = fields.Many2one('product.product', string='Odoo Ürünü')
