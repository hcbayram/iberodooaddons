from odoo import models, fields, api, _
class UBLInvoiceLine(models.Model):
    _inherit = "l10n_tr.ubl.invoiceline"


    product_type = fields.Selection(
        string='Ürün tipi',
        selection=[('ILAC', 'İlaç'), ('TIBBICIHAZ', 'Tıbbi Cihaz'), ('DIGER', 'Diğer')]
    )
    

  