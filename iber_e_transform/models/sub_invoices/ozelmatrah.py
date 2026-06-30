from odoo import models, fields, api, _
class UBLInvoiceLine(models.Model):
    _inherit = "l10n_tr.ubl.invoiceline"


    special_base_amount = fields.Float("Special Base Amount")

    def _get_base_amount(self):
        res = super()._get_base_amount()
        self.ensure_one()
        if self.special_base_amount and self.base_document_id.document_type_code == 'OZELMATRAH':
            res = self.special_base_amount
        return res
    
    @api.depends("special_base_amount")
    def _compute_line_amount(self):
        super()._compute_line_amount()