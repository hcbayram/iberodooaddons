from odoo import models, fields


class UBLInvoiceSupplierID(models.Model):
    _name = "l10n_tr.ubl.invoice.supplier.id"
    _inherit = "algebra.base.document.supplier.extra.id"
    _description = "Supplier Extra Identification"

    base_document_id = fields.Many2one(
        "l10n_tr.ubl.invoice",
        string="Invoice",
        required=True,
        ondelete="cascade",
    )
