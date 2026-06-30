from odoo import models, fields


class UBLInvoiceCustomerID(models.Model):
    _name = "l10n_tr.ubl.invoice.customer.id"
    _inherit = "algebra.base.document.customer.extra.id"
    _description = "Customer Extra Identification"

    base_document_id = fields.Many2one(
        "l10n_tr.ubl.invoice",
        string="Invoice",
        required=True,
        ondelete="cascade",
    )
