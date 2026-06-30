from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    iber_mrp_single_entry = fields.Boolean(
        related='company_id.iber_mrp_single_entry',
        readonly=False,
        string='Üretim Muhasebesi Tek Fiş',
    )
