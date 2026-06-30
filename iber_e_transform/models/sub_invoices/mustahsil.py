from odoo import models, fields, api, _

class UBLInvoice(models.Model):
    _inherit = "l10n_tr.ubl.invoice"

    
    ActualDeliveryDate = fields.Date(string="Actual Delivery Date", help="Actual Delivery Date for Export Invoices")









