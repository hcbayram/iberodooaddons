from odoo import models, fields, api
from odoo.exceptions import UserError


class EDNInvoiceSeries(models.Model):
    """
    Entegratörden çekilen fatura/irsaliye serileri.
    Seçilen seri, UBL belge numarası oluşturulurken prefix olarak kullanılır.
    """
    _name = "edn.invoice.series"
    _description = "e-Transformation Series Codes"
    _order = "document_type, prefix"
    _rec_name = "prefix"

    integrator_id = fields.Many2one(
        "edn.integrator",
        string="Integrator",
        required=True,
        ondelete="cascade",
    )
    prefix = fields.Char("Series Prefix", required=True, help="3 uppercase letters, e.g.: IBR")
    document_type = fields.Selection(
        [
            ("invoice", "e-Invoice"),
            ("earchive", "e-Archive Invoice"),
            ("despatch", "e-Despatch"),
        ],
        string="Document Type",
        required=True,
        default="invoice",
    )
    description = fields.Char("Description")
    raw_data = fields.Text("Raw Data (JSON)")
    active = fields.Boolean("Active", default=True)

    _sql_constraints = [
        (
            "prefix_type_integrator_unique",
            "unique(integrator_id, prefix, document_type)",
            "This prefix/type combination already exists for this integrator.",
        )
    ]

    def name_get(self):
        result = []
        for rec in self:
            label = f"[{rec.prefix}] {dict(self._fields['document_type'].selection).get(rec.document_type, '')}"
            result.append((rec.id, label))
        return result
