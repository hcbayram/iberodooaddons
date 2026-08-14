from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EDocumentBaseLine(models.Model):
    _name = "algebra.base.document.line"
    _description = "UBL-TR Document Line"

    base_document_id = fields.Many2one(
        "algebra.base.document", string="Invoice", ondelete="cascade", index=True, required=True
    )
    document_type_code = fields.Char(
        related="base_document_id.document_type_code", readonly=True, store=False
    )
    profile_code = fields.Char(
        related="base_document_id.profile_code", readonly=True, store=False
    )
    name = fields.Char("Name", required=True)
    quantity = fields.Float("Quantity", required=True, default=1.0)
    unit_code_id = fields.Many2one(
        "algebra.base.document.unit",
        string="Unit",
        required=True,
        index=True,
        help="UBL standard unit code",
    )
    unit_code = fields.Char(
        string="Unit Code",
        related="unit_code_id.code",
        readonly=True,
        store=True,
        help="UBL unit code (derived from unit_code_id)",
    )
    currency_id = fields.Many2one("res.currency", string="Currency", required=True)
    price_amount = fields.Float("Unit Price", digits="Product Price", required=True)
    line_extension_amount = fields.Float(
        "Line Amount",
        digits="Percentage Analytic",
        compute="_compute_line_amount",
        store=True,
    )
    description = fields.Text("Description")
    brandName = fields.Char("Brand Name")
    modelName = fields.Char("Model Name")
    buyersItemId = fields.Char("Buyer's Item ID")
    sellersItemId = fields.Char("Seller's Item ID")
    manufacturerItemId = fields.Char("Manufacturer's Item ID")

    @api.depends("quantity", "price_amount")
    def _compute_line_amount(self):
        for rec in self:
            rec.line_extension_amount = (rec.quantity * rec.price_amount) or 0.0

    def open_line_details(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Line Details",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
