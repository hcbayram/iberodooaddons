from odoo import models, fields, api, _


class UBLInvoiceIade(models.Model):
    _inherit = "l10n_tr.ubl.invoice"

    return_reference_ids = fields.One2many(
        "l10n_tr.ubl.return.reference",
        "base_document_id",
        string="Return References",
    )


class UBLReturnReference(models.Model):
    _name = "l10n_tr.ubl.return.reference"
    _description = "UBL-TR Return Reference"

    base_document_id = fields.Many2one(
        "l10n_tr.ubl.invoice", string="Invoice", ondelete="cascade", index=True, required=True
    )
    invoice_number = fields.Char("Base Invoice Number", required=True)
    issue_date = fields.Date("Base Invoice Issue Date")
