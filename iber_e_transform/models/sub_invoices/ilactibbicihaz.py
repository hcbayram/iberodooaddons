from odoo import models, fields, api, _
class UBLInvoiceLine(models.Model):
    _inherit = "l10n_tr.ubl.invoiceline"


    product_type = fields.Selection(
        string='Product Type',
        selection=[('ILAC', 'Medicine'), ('TIBBICIHAZ', 'Medical Device'), ('DIGER', 'Other')]
    )
    

  