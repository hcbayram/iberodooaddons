from odoo import models, fields, api


class IberTicimaxOrderLine(models.Model):
    _name = 'iber.ticimax.order.line'
    _description = 'Ticimax Sipariş Kalemi'
    _rec_name = 'urun_adi'

    order_id = fields.Many2one(
        'iber.ticimax.order', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='order_id.company_id', store=True)

    ticimax_urun_id = fields.Integer(string='Ticimax Ürün ID', readonly=True)
    urun_adi = fields.Char(string='Ürün Adı', readonly=True)
    stok_kodu = fields.Char(string='Stok Kodu', readonly=True)
    barkod = fields.Char(string='Barkod', readonly=True)
    adet = fields.Float(string='Adet', readonly=True, digits=(12, 2))
    tutar = fields.Float(string='Birim Fiyat', readonly=True, digits=(12, 2))
    kdv_orani = fields.Float(string='KDV Oranı (%)', readonly=True, digits=(5, 2))
    kdv_tutari = fields.Float(string='KDV Tutarı', readonly=True, digits=(12, 2))
    toplam = fields.Float(
        string='Toplam', compute='_compute_toplam', store=True, digits=(12, 2))

    @api.depends('tutar', 'adet')
    def _compute_toplam(self):
        for rec in self:
            rec.toplam = rec.tutar * rec.adet
