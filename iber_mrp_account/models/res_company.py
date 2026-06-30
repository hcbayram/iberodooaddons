from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    iber_mrp_single_entry = fields.Boolean(
        string='Üretim Muhasebesi Tek Fiş',
        default=False,
        help="Etkinleştirildiğinde bir üretim emrindeki tüm yevmiye kayıtları "
             "(711/150, 151/711, 151/721-731, 152/151) tek bir fişte birleştirilir. "
             "Kapalıyken her kayıt ayrı fiş olarak oluşur.",
    )
    account_wip_711_721_731_id = fields.Many2one(
        'account.account',
        string='WIP Yansıtma Hesabı (151)',
        ondelete='restrict',
        domain="[('active', '=', True)]",
        help="711 hesabının MO tamamlandığında aktarılacağı WIP hesabı (151). "
             "Boş bırakılırsa üretim lokasyonunun valuation_account_id'si kullanılır.",
    )
