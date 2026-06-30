from odoo import models, fields
from ..core.trendyol_const import ORDER_STATUSES


class IberTrendyolOrderLine(models.Model):
    _name = 'iber.marketplace.trendyol.order.line'
    _description = 'Trendyol Sipariş Kalemi'
    _rec_name = 'product_name'

    order_id = fields.Many2one(
        'iber.marketplace.trendyol.order', required=True,
        ondelete='cascade', string='Sipariş')
    config_id = fields.Many2one(
        related='order_id.config_id', store=True, string='Bağlantı')
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, string='Şirket')

    # Trendyol satır alanları
    trendyol_line_id = fields.Integer(
        readonly=True, string='Trendyol Satır ID')
    barcode = fields.Char(readonly=True, string='Barkod')
    merchant_sku = fields.Char(readonly=True, string='Tedarikçi SKU')
    product_name = fields.Char(readonly=True, string='Ürün Adı')
    quantity = fields.Float(readonly=True, string='Miktar')
    price = fields.Float(readonly=True, string='Birim Fiyat')
    discount_details = fields.Char(readonly=True, string='İndirim Detayı')
    status = fields.Selection(
        selection=ORDER_STATUSES,
        readonly=True, string='Durum')
    cargo_provider_name = fields.Char(readonly=True, string='Kargo Şirketi')
    cargo_tracking_number = fields.Char(readonly=True, string='Kargo Takip No')

    # Odoo ürün eşleşmesi
    product_id = fields.Many2one('product.product', string='Odoo Ürünü')
