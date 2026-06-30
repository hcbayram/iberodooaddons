from odoo import models, fields, api
from odoo.exceptions import UserError


class EDNInvoiceSeries(models.Model):
    """
    Entegratörden çekilen fatura/irsaliye serileri.
    Seçilen seri, UBL belge numarası oluşturulurken prefix olarak kullanılır.
    """
    _name = "edn.invoice.series"
    _description = "E-Dönüşüm Seri Kodları"
    _order = "document_type, prefix"
    _rec_name = "prefix"

    integrator_id = fields.Many2one(
        "edn.integrator",
        string="Entegratör",
        required=True,
        ondelete="cascade",
    )
    prefix = fields.Char("Seri Prefix", required=True, help="3 büyük harf, örn: IBR")
    document_type = fields.Selection(
        [
            ("invoice", "e-Fatura"),
            ("earchive", "e-Arşiv Fatura"),
            ("despatch", "e-İrsaliye"),
        ],
        string="Belge Türü",
        required=True,
        default="invoice",
    )
    description = fields.Char("Açıklama")
    raw_data = fields.Text("Ham Veri (JSON)")
    active = fields.Boolean("Aktif", default=True)

    _sql_constraints = [
        (
            "prefix_type_integrator_unique",
            "unique(integrator_id, prefix, document_type)",
            "Bu entegratör için aynı prefix/tür kombinasyonu zaten mevcut.",
        )
    ]

    def name_get(self):
        result = []
        for rec in self:
            label = f"[{rec.prefix}] {dict(self._fields['document_type'].selection).get(rec.document_type, '')}"
            result.append((rec.id, label))
        return result
