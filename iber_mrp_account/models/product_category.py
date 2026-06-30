from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    property_account_710_id = fields.Many2one(
        'account.account',
        string='710 Direkt Hammadde Giderleri',
        company_dependent=True,
        ondelete='restrict',
        help="Hammadde üretime gönderildiğinde BORÇ kaydedilir. Fiş: DR 710 / CR 150",
    )
    property_account_711_id = fields.Many2one(
        'account.account',
        string='711 Direkt Hammadde Yansıtma',
        company_dependent=True,
        ondelete='restrict',
        help="MO tamamlandığında 151'e yansıtmada ALACAK kaydedilir. Fiş: DR 151 / CR 711",
    )
