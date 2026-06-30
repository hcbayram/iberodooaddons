from odoo import models, fields, api, _

TEVKIFAT_KODLARI = [
    ("601", "601 - Hizmet alımlarında 5/10 KDV tevkifatı"),
    ("602", "602 - Temizlik, bahçe bakım 7/10 KDV tevkifatı"),
    ("603", "603 - Yapım işleri 3/10 KDV tevkifatı"),
    ("604", "604 - Spor, eğlence hizmeti 9/10 KDV tevkifatı"),
    ("9015", "9015 - Serbest meslek hizmeti 7/10 KDV tevkifatı"),
]


class UBLInvoiceLineAdjustment(models.Model):
    _name = "l10n_tr.ubl.invoiceline.adjustment"
    _description = "Invoice Line Discount / Surcharge"

    line_id = fields.Many2one(
        "l10n_tr.ubl.invoiceline", string="Invoice Line", ondelete="cascade", required=True, index=True
    )
    type = fields.Selection(
        [("discount", "İndirim"), ("surcharge", "Arttırım")],
        string="Tür",
        required=True,
    )
    rate = fields.Float("Oran (%)")
    base_amount = fields.Float("Baz Tutar", digits="Percentage Analytic", readonly=True)
    amount = fields.Float("Amount", compute="_compute_amount", inverse="_inverse_amount", store=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Para Birimi",
        related="line_id.currency_id",
        store=True,
        readonly=True,
    )
    description = fields.Char("Açıklama")

    @api.depends("rate", "line_id.line_extension_amount")
    def _compute_amount(self):
        for rec in self:
            base = rec.base_amount or 0.0
            rec.amount = base * (rec.rate / 100.0) if rec.rate else 0.0

    def _inverse_amount(self):
        for rec in self:
            base = rec.base_amount or 0.0
            rec.rate = (rec.amount / base) * 100.0 if rec.amount and base else 0.0

    @api.onchange("line_id")
    def _onchange_compute_base_amount(self):
        previous_lines = self.line_id.adjustment_ids - self
        if previous_lines:
            base = (self.line_id.price_amount * self.line_id.quantity) or 0.0
            for prev in previous_lines:
                base = base - (base * (prev.rate / 100))
            self.base_amount = base
        elif self.line_id:
            self.base_amount = (self.line_id.price_amount * self.line_id.quantity) or 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            line_id = vals.get("line_id")
            if line_id:
                previous_line = self.search([("line_id", "=", line_id)], order="id desc", limit=1)
                if previous_line:
                    vals["base_amount"] = previous_line.base_amount - previous_line.amount
                else:
                    line = self.env["l10n_tr.ubl.invoiceline"].browse(line_id)
                    vals["base_amount"] = line.line_extension_amount or 0.0
        return super().create(vals_list)


class UBLTaxType(models.Model):
    _name = "l10n_tr.ubl.tax.type"
    _description = "UBL Tax Types (KDV, Tevkifat, Stopaj, etc.)"

    code = fields.Char("Code", required=True)
    name = fields.Char("Name", required=True)
    notes = fields.Text("Notes")
    type = fields.Selection(
        [("base", "Tutar"), ("vat", "KDV"), ("otv", "Tutar + KDV")],
        string="Type",
        required=True,
    )
    description = fields.Char("Description")

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code} — {rec.name}"


class UBLInvoiceLineTaxExtra(models.Model):
    _name = "l10n_tr.ubl.invoiceline.taxextra"
    _description = "Invoice Line Extra Taxes"

    line_id = fields.Many2one("l10n_tr.ubl.invoiceline", required=True, ondelete="cascade")
    tax_type_id = fields.Many2one("l10n_tr.ubl.tax.type", string="Vergi Kodu", required=True)
    rate = fields.Float("Oran (%)")
    taxable_amount = fields.Float(
        "Vergi Baz Tutar", digits="Percentage Analytic", compute="_compute_amount", store=True
    )
    amount = fields.Float(
        "Tutar", digits="Percentage Analytic", compute="_compute_amount", store=True
    )
    currency_id = fields.Many2one(related="line_id.currency_id", store=False)

    @api.depends("rate", "line_id.line_extension_amount")
    def _compute_amount(self):
        for rec in self:
            base = rec.line_id.line_extension_amount or 0.0
            if rec.rate:
                rec.taxable_amount = base
                rec.amount = base * (rec.rate / 100.0)
            else:
                rec.taxable_amount = 0.0
                rec.amount = 0.0


class UBLInvoiceLine(models.Model):
    _name = "l10n_tr.ubl.invoiceline"
    _description = "UBL-TR Invoice Line"
    _inherit = "algebra.base.document.line"

    base_document_id = fields.Many2one(
        "l10n_tr.ubl.invoice", string="Invoice", ondelete="cascade", index=True, required=True
    )
    tax_percent = fields.Float("Tax %", default=20.0)
    tax_amount = fields.Float(
        "Tax Amount", digits="Percentage Analytic", compute="_compute_line_amount", store=True
    )
    tax_category_code = fields.Char("Tax Category Code", default="S")
    tax_scheme_code = fields.Char("Tax Scheme Code", default="0015")
    tax_scheme_name = fields.Char("Tax Scheme Name", default="KDV")
    withholding_rate = fields.Float("Tevkifat %", default=0.0)
    withholding_amount = fields.Float(
        "Tevkifat Tutarı", digits="Percentage Analytic", compute="_compute_line_amount", store=True
    )
    income_withholding_rate = fields.Float("Stopaj %", default=0.0)
    income_withholding_amount = fields.Float(
        "Stopaj Tutarı", digits="Percentage Analytic", compute="_compute_line_amount", store=True
    )
    withholding_code = fields.Selection(TEVKIFAT_KODLARI, string="Tevkifat Kodu")
    line_note_ids = fields.One2many(
        "l10n_tr.ubl.invoiceline.note", "line_id", string="Line Notes"
    )
    adjustment_ids = fields.One2many(
        "l10n_tr.ubl.invoiceline.adjustment", "line_id", string="Adjustments"
    )
    taxextra_ids = fields.One2many(
        "l10n_tr.ubl.invoiceline.taxextra", "line_id", string="Extra Taxes (Stopaj, Diğer)"
    )
    tax_exemption_reason_id = fields.Many2one("tax.exemption.reason", string="KDV İstisna Sebebi")
    tax_exemption_reason_code = fields.Char(
        related="tax_exemption_reason_id.code", string="KDV İstisna Sebep Kodu"
    )

    def write(self, vals):
        res = super().write(vals)
        self.base_document_id._rebuild_subtotals()
        return res

    @api.depends("withholding_rate", "income_withholding_rate", "tax_percent", "adjustment_ids")
    def _compute_line_amount(self):
        for rec in self:
            rec.line_extension_amount = (rec.quantity * rec.price_amount or 0.0) - (
                sum(rec.adjustment_ids.mapped("amount")) or 0.0
            )
            base = rec.line_extension_amount or 0.0
            rec.tax_amount = base * (rec.tax_percent or 0.0) / 100.0
            rec.withholding_amount = rec.tax_amount * (rec.withholding_rate or 0.0) / 100.0
            rec.income_withholding_amount = base * (rec.income_withholding_rate or 0.0) / 100.0

    def open_line_notes(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Satır Notları"),
            "res_model": "l10n_tr.ubl.invoiceline.note",
            "view_mode": "list",
            "views": [
                (self.env.ref("iber_e_transform.view_invoiceline_note_list").id, "list"),
            ],
            "domain": [("line_id", "=", self.id)],
            "context": {"default_line_id": self.id},
            "target": "new",
        }


class UBLInvoiceLineNote(models.Model):
    _name = "l10n_tr.ubl.invoiceline.note"
    _description = "UBL Invoice Line Notes"
    _order = "sequence,id"

    line_id = fields.Many2one(
        "l10n_tr.ubl.invoiceline", string="Line", ondelete="cascade", required=True
    )
    sequence = fields.Integer(default=10)
    note = fields.Text("Line Note", required=True)

    def action_save_note(self):
        return {"type": "ir.actions.act_window_close"}


class TaxExemptionReason(models.Model):
    _name = "tax.exemption.reason"
    _description = "KDV İstisna Sebebi"

    code = fields.Char(required=True)
    name = fields.Char(required=True)
    invoice_type = fields.Selection(
        [
            ("ISTISNA", "İstisna"),
            ("IHRACAT", "İhracat"),
            ("IHRACKAYITLI", "İhracat Kayıtlı"),
            ("OZELMATRAH", "Özel Matrah"),
            ("YOLCUBERABERI", "Yolcu Beraberi"),
        ],
        required=True,
    )
