import json
import requests
from odoo import models, fields, api, _
from datetime import date
import base64
from odoo.exceptions import UserError
from odoo.tools.misc import file_path
import subprocess
import uuid as uuid_engine
import logging

_logger = logging.getLogger(__name__)

try:
    from lxml import etree
    LXML_AVAILABLE = True
except Exception:
    import xml.etree.ElementTree as etree  # type: ignore
    LXML_AVAILABLE = False

try:
    from ...utils.xslt_helper import xslt2_transform
    XSLT_AVAILABLE = True
except Exception:
    XSLT_AVAILABLE = False
    def xslt2_transform(xml_string, xslt_path):
        raise NotImplementedError("xslt_helper module could not be loaded. Is Saxon/lxml installed?")


class UBLTaxSubtotal(models.Model):
    _name = "l10n_tr.ubl.taxsubtotal"
    _description = "UBL-TR Tax Subtotal"

    name = fields.Char("Name", default="KDV", required=True)
    percent = fields.Float("Rate (%)", required=True)
    tax_amount = fields.Float("Tax Amount", digits="Percentage Analytic", required=True)
    taxable_amount = fields.Float("Taxable Amount", digits="Percentage Analytic", required=True)
    tax_category_code = fields.Char("Tax Category Code", default="S")
    tax_scheme_name = fields.Char("Tax Scheme Name", default="KDV")
    tax_scheme_code = fields.Char("Tax Scheme Code", default="0015")
    currency_id = fields.Many2one("res.currency", string="Currency", required=True)
    invoice_id = fields.Many2one("l10n_tr.ubl.invoice", string="Invoice", ondelete="cascade", index=True)
    kind = fields.Selection(
        [
            ("vat", "VAT"),
            ("withholding_vat", "VAT Withholding"),
            ("others", "Other Taxes and Withholdings"),
        ],
        default="vat",
        required=True,
        index=True,
    )


class UBLDespatchDocumentReference(models.Model):
    _name = "l10n_tr.ubl.despatch.reference"
    _description = "UBL-TR Despatch Document Reference"

    invoice_id = fields.Many2one(
        "l10n_tr.ubl.invoice", string="Invoice", ondelete="cascade", index=True, required=True
    )
    despatch_id = fields.Char("Despatch Document ID", required=True)
    issue_date = fields.Date("Despatch Issue Date")
    note = fields.Char("Description / Note")


class InvoicePreviewWizard(models.TransientModel):
    _name = "l10n_tr.ubl.invoice.preview.wizard"
    _description = "UBL Invoice Preview"

    html_content = fields.Html("Invoice HTML")


class UBLInvoicePreviewWizard(models.TransientModel):
    _name = "l10n_tr.ubl.invoice.pdf.preview.wizard"
    _description = "UBL Invoice PDF Preview Wizard"

    pdf_data = fields.Binary("PDF", readonly=True, attachment=False)


class UBLInvoice(models.Model):
    _name = "l10n_tr.ubl.invoice"
    _inherits = {"algebra.base.document": "base_document_id"}
    _inherit = ["algebra.base.e_document_base_methods"]
    _description = "UBL-TR 2.1 Invoice"
    _rec_name = "id_value"

    _xslt_path = "iber_e_transform/static/xslt/general.xslt"
    _profile_id_type = "invoice"

    base_document_id = fields.Many2one(
        "algebra.base.document",
        string="Base Document",
        auto_join=True,
        index=True,
        ondelete="cascade",
        required=True,
    )
    _sql_constraints = [
        ("unique_base_id", "unique(base_document_id)", "Each base document must have only one sub record!"),
    ]

    invoice_direction = fields.Selection(
        [("incoming", "Incoming Invoice"), ("outgoing", "Outgoing Invoice")],
        string="Invoice Direction",
        default="outgoing",
        required=True,
    )
    note = fields.Text("Note")

    # Odoo 19 native bağlantısı (Seçenek A: bağımsız kayıt)
    account_move_id = fields.Many2one(
        "account.move",
        string="System Invoice",
        index=True,
        ondelete="set null",
        help="The System invoice record that is the source of this UBL invoice",
    )

    line_ids = fields.One2many("l10n_tr.ubl.invoiceline", "base_document_id", string="Lines")
    subtotal_ids = fields.One2many("l10n_tr.ubl.taxsubtotal", "invoice_id", string="Tax Subtotals")

    line_extension_total = fields.Float(
        digits="Percentage Analytic", compute="_compute_totals", store=True, readonly=True
    )
    total_without_tax = fields.Float(
        digits="Percentage Analytic", compute="_compute_totals", store=True, readonly=True
    )
    total_with_tax = fields.Float(
        digits="Percentage Analytic", compute="_compute_totals", store=True, readonly=True
    )
    tax_total_amount = fields.Float(
        digits="Percentage Analytic", compute="_compute_totals", store=True, readonly=True
    )
    allowance_total_amount = fields.Float(
        digits="Percentage Analytic", compute="_compute_totals", store=True, readonly=True
    )
    payable_amount = fields.Float(
        digits="Percentage Analytic", compute="_compute_totals", store=True, readonly=True
    )
    withholding_tax_total = fields.Float(
        digits="Percentage Analytic",
        compute="_compute_totals",
        store=True,
        readonly=True,
        string="Withholding Total",
    )
    income_withholding_total = fields.Float(
        digits="Percentage Analytic",
        compute="_compute_totals",
        store=True,
        readonly=True,
        string="Income Withholding Total",
    )

    # Backward-compat aliases
    line_extension_amount = fields.Float(
        digits="Percentage Analytic", related="line_extension_total", store=True, readonly=True
    )
    tax_exclusive_amount = fields.Float(
        digits="Percentage Analytic", related="total_without_tax", store=True, readonly=True
    )
    tax_inclusive_amount = fields.Float(
        digits="Percentage Analytic", related="total_with_tax", store=True, readonly=True
    )

    subtotal_vat_ids = fields.One2many(
        "l10n_tr.ubl.taxsubtotal",
        "invoice_id",
        string="VAT Subtotals",
        compute="_compute_filtered_subtotals",
        store=False,
    )
    subtotal_withholding_vat_ids = fields.One2many(
        "l10n_tr.ubl.taxsubtotal",
        "invoice_id",
        string="Withholding Subtotals",
        compute="_compute_filtered_subtotals",
        store=False,
    )
    subtotal_withholding_income_ids = fields.One2many(
        "l10n_tr.ubl.taxsubtotal",
        "invoice_id",
        string="Income Withholding Subtotals",
        compute="_compute_filtered_subtotals",
        store=False,
    )
    despatch_reference_ids = fields.One2many(
        "l10n_tr.ubl.despatch.reference", "invoice_id", string="Despatch Document References"
    )

    # PaymentMeans
    PaymentMeansCode = fields.Selection(
        [
            ("1", "Ödeme Tipi Muhtelif"),
            ("10", "Nakit"),
            ("20", "Çek"),
            ("23", "Banka Çeki"),
            ("42", "Havale/EFT"),
            ("48", "Kredi Kartı/Banka Kartı"),
        ],
        string="Payment Means Code",
    )
    PaymentDueDate = fields.Date("Payment Due Date")
    PaymentChannelCode = fields.Selection(
        [
            ("1", "Posta"), ("2", "Hava Yolu ile Posta"), ("3", "Telgraf"),
            ("4", "Teleks"), ("5", "SWIFT"), ("6", "Diğer İletişim Ağları"),
            ("7", "Tanımlı Olmayan Ağlar"), ("8", "Fedwire"), ("9", "Bankada Elle"),
            ("10", "Taahhütlü Hava Yolu ile Posta"), ("11", "Taahhütlü Posta"),
            ("12", "Kurye"), ("13", "Özel Kurye"), ("14", "Uluslararası Para Transferi"),
            ("15", "Ulusal Para Transferi"), ("ZZZ", "Karşılıklı Olarak Belirlenen Yol"),
        ],
        string="Payment Channel Code",
    )
    InstructionNote = fields.Char("Instruction Note")
    PayeeFinancialAccount = fields.Char("Payee Financial Account")
    PaymentTermsNote = fields.Char("Payment Terms Note")
    PenaltySurchargePercent = fields.Float("Penalty Surcharge Percent")
    PenaltyAmount = fields.Float("Penalty Amount", digits="Percentage Analytic")
    PTPaymentDueDate = fields.Date("Payment Due Date (PT)")

    # OKC
    okc_fis_no = fields.Char("OKC Receipt No")
    okc_fis_tarih_saat = fields.Datetime("OKC Receipt Date/Time")
    okc_z_rapor_no = fields.Char("OKC Z Report No")
    okc_seri_no = fields.Char("OKC Serial No")
    okc_fis_tipi = fields.Selection(
        [
            ("AVANS", "Avans"), ("YEMEK_FIS", "Yemek Fişi Tahsilatı"),
            ("E-FATURA", "E-fatura"), ("E-FATURA_IRSALIYE", "İrsaliye Yerine Geçen E-Fatura"),
            ("E-ARSIV", "E-Arşiv Fatura"), ("E-ARSIV_IRSALIYE", "İrsaliye Yerine Geçen E-Arşiv Fatura"),
            ("FATURA", "Fatura"), ("OTOPARK", "Otopark"),
            ("FATURA_TAHSILAT", "Fatura Tahsilatı İşlemleri"),
            ("FATURA_TAHSILAT_KOMISYONLU", "Komisyonlu Fatura Tahsilatı İşlemleri"),
        ],
        string="OKC Receipt Type",
    )

    def copy(self, default=None):
        default = dict(default or {})
        new_base = self.base_document_id.copy()
        default["base_document_id"] = new_base.id
        return super().copy(default)

    @api.onchange("document_type_code", "profile_id")
    def _onchange_document_type_code(self):
        self.ensure_one()
        if self.document_type_code == "IADE":
            if self.profile_id.code not in ["EARSIVFATURA", "TEMELFATURA", "ILAC_TIBBICIHAZ"]:
                raise UserError(
                    _("Return-type invoices can only be used with e-Archive, Basic Invoice, and Pharmaceutical/Medical Device profiles.")
                )

    def _get_profile_id_domain(self):
        return [("profile_type", "=", self._profile_id_type)]

    @api.depends("subtotal_ids.kind")
    def _compute_filtered_subtotals(self):
        for inv in self:
            inv.subtotal_vat_ids = inv.subtotal_ids.filtered(lambda s: s.kind == "vat")
            inv.subtotal_withholding_vat_ids = inv.subtotal_ids.filtered(lambda s: s.kind == "withholding_vat")
            inv.subtotal_withholding_income_ids = inv.subtotal_ids.filtered(lambda s: s.kind == "others")

    @api.depends(
        "line_ids.line_extension_amount",
        "line_ids.tax_percent",
        "line_ids.withholding_amount",
        "line_ids.income_withholding_amount",
        "line_ids.adjustment_ids",
        "line_ids.taxextra_ids.amount",
        "line_ids.taxextra_ids.tax_type_id",
        "document_currency_id",
    )
    def _compute_totals(self):
        for inv in self:
            line_total = sum(inv.line_ids.mapped("line_extension_amount")) or 0.0
            tax_total = 0.0
            for line in inv.line_ids:
                base = line.line_extension_amount or 0.0
                if base:
                    tax_total += base * (line.tax_percent or 0.0) / 100.0
                # ÖTV/Konaklama Vergisi gibi KDV dışındaki vergiler de toplama dahil edilir
                for tax in line.taxextra_ids:
                    if tax.tax_type_id and tax.tax_type_id.type in ("base", "otv"):
                        tax_total += tax.amount or 0.0
            withholding_total = sum(inv.line_ids.mapped("withholding_amount")) or 0.0
            income_withholding_total = sum(inv.line_ids.mapped("income_withholding_amount")) or 0.0
            inv.allowance_total_amount = sum(inv.line_ids.adjustment_ids.mapped("amount")) or 0.0
            inv.line_extension_total = line_total + inv.allowance_total_amount
            inv.total_without_tax = line_total
            inv.tax_total_amount = tax_total
            inv.total_with_tax = line_total + tax_total
            inv.payable_amount = (inv.total_with_tax or 0.0) - withholding_total - income_withholding_total
            inv.withholding_tax_total = withholding_total
            inv.income_withholding_total = income_withholding_total

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("id_value"):
                vals["id_value"] = self._next_invoice_number()
        recs = super().create(vals_list)
        recs._rebuild_subtotals()
        return recs

    @api.model
    def _next_invoice_number(self) -> str:
        """
        Varsayılan seri ayarlıysa o prefix ile GIB uyumlu numara üretir.
        Ayarlı değilse sequence'dan alır.
        """
        try:
            settings = self.env["ubl21.config.settings"].get_singleton()
            series = getattr(settings, "default_invoice_series_id", None)
            if series and series.prefix:
                import datetime
                year = datetime.date.today().year
                seq = self.env["ir.sequence"].next_by_code("l10n_tr.ubl.invoice") or "000000001"
                # Sadece rakam kısmını al ve 9 haneye pad'le
                digits = "".join(filter(str.isdigit, str(seq))).zfill(9)[-9:]
                return f"{series.prefix.upper()}{year}{digits}"
        except Exception:
            pass
        return self.env["ir.sequence"].next_by_code("l10n_tr.ubl.invoice") or "/"

    def write(self, vals):
        res = super().write(vals)
        self._rebuild_subtotals()
        return res

    def _rebuild_subtotals(self):
        for inv in self:
            groups_vat = {}
            groups_withholding_vat = {}
            groups_withholding_income = {}

            for line in inv.line_ids:
                base = line.line_extension_amount or 0.0
                if not base:
                    continue

                rate = line.tax_percent or 0.0
                key_vat = (rate, line.tax_scheme_code or "0015", line.tax_category_code or "S", line.tax_scheme_name or "KDV")
                groups_vat.setdefault(key_vat, {"base": 0.0, "tax": 0.0})
                groups_vat[key_vat]["base"] += base
                groups_vat[key_vat]["tax"] += base * rate / 100.0

                if (line.withholding_rate or 0.0) > 0:
                    base_wh = base * rate / 100.0
                    key_w = (line.withholding_rate, line.withholding_code, "S", "KDV Tevkifat")
                    groups_withholding_vat.setdefault(key_w, {"base": 0.0, "tax": 0.0})
                    groups_withholding_vat[key_w]["base"] += base_wh
                    groups_withholding_vat[key_w]["tax"] += base_wh * (line.withholding_rate or 0.0) / 100.0

                for tax in line.taxextra_ids:
                    if tax.tax_type_id and tax.tax_type_id.type in ("base", "otv"):
                        key_i = (tax.rate, tax.tax_type_id.code, "S", tax.tax_type_id.name)
                        groups_withholding_income.setdefault(key_i, {"base": 0.0, "tax": 0.0})
                        groups_withholding_income[key_i]["base"] += base
                        groups_withholding_income[key_i]["tax"] += base * (tax.rate or 0.0) / 100.0

            inv.subtotal_ids.unlink()

            for (rate, scheme_code, cat_code, scheme_name), agg in groups_vat.items():
                self.env["l10n_tr.ubl.taxsubtotal"].create({
                    "invoice_id": inv.id,
                    "currency_id": inv.document_currency_id.id,
                    "percent": rate,
                    "taxable_amount": agg["base"],
                    "tax_amount": agg["tax"],
                    "tax_category_code": cat_code,
                    "tax_scheme_code": scheme_code,
                    "tax_scheme_name": scheme_name,
                    "name": "KDV",
                    "kind": "vat",
                })

            for (rate, scheme_code, cat_code, scheme_name), agg in groups_withholding_vat.items():
                self.env["l10n_tr.ubl.taxsubtotal"].create({
                    "invoice_id": inv.id,
                    "currency_id": inv.document_currency_id.id,
                    "percent": rate,
                    "taxable_amount": agg["base"],
                    "tax_amount": agg["tax"],
                    "tax_category_code": cat_code,
                    "tax_scheme_code": scheme_code,
                    "tax_scheme_name": scheme_name,
                    "name": "Tevkifat",
                    "kind": "withholding_vat",
                })

            for (rate, scheme_code, cat_code, scheme_name), agg in groups_withholding_income.items():
                self.env["l10n_tr.ubl.taxsubtotal"].create({
                    "invoice_id": inv.id,
                    "currency_id": inv.document_currency_id.id,
                    "percent": rate,
                    "taxable_amount": agg["base"],
                    "tax_amount": agg["tax"],
                    "tax_category_code": cat_code,
                    "tax_scheme_code": scheme_code,
                    "tax_scheme_name": scheme_name,
                    "name": scheme_name or "Diğer Vergi",
                    "kind": "others",
                })

    def check_document_validity(self):
        super().check_document_validity()
        self.ensure_one()
        if self.document_type_code in ["IADE", "TEVKIFATIADE"]:
            if not self.return_reference_ids:
                raise UserError("Return-type invoices must have at least one Return Reference.")
            if any(not ref.issue_date for ref in self.return_reference_ids):
                raise UserError("Return Reference issue date cannot be empty.")
            if any(len(ref.invoice_number) != 16 for ref in self.return_reference_ids):
                raise UserError("Return Reference numbers must be 16 characters long.")
            if any(ref.issue_date > date.today() for ref in self.return_reference_ids):
                raise UserError("Return Reference issue date cannot be later than today.")

    def action_send_to_ubl_service(self):
        self.ensure_one()
        self.check_document_validity()
        xml_response = self._get_xml_from_service()
        json_payload = self.to_json()
        if not xml_response:
            raise UserError("Could not fetch XML from the service!")
        settings = self.env["ubl21.config.settings"].get_singleton()
        integrator_info = {
            "IntegratorCode": settings.integrator_id.code if settings and settings.integrator_id else "NES",
            "test_mode": settings.test_mode if settings else False,
            "user_name": settings.user_name if settings else "",
            "user_password": settings.user_password if settings else "",
            "api_token": settings.api_token if settings else "",
        }
        payload = {
            "IntegratorInfo": integrator_info,
            "DocumentType": "Invoice",
            "DocumentProfile": self.profile_id.code,
            "File": xml_response,
            "JsonPayload": json_payload,
            "UUID": self.UUID,
            "IsDirectSend": True,
            "PreviewType": "None",
            "SenderAlias": settings.erp_sender_alias,
            "ReceiverAlias": self.customer_receiver_alias,
            "CustomerRegisterNumber": self.customer_vkn_tckn,
        }

        # edn.document.manager varsa doğrudan çağır (HTTP bypass)
        try:
            if "edn.document.manager" in self.env:
                resp_data = self.env["edn.document.manager"].sudo().send_document(payload)
            else:
                # HTTP fallback (farklı instance)
                url = self._get_service_url().rstrip("/") + "/send_ubl_xml"
                response = requests.post(url, headers=self._service_headers(), data=json.dumps(payload))
                if response.status_code != 200:
                    raise UserError(
                        _("Service returned an error (HTTP %s):\n%s") % (response.status_code, response.text[:300])
                    )
                resp_data = response.json()

            integrator_ok = resp_data.get("ok", True)
            integrator_error = resp_data.get("error") or ""
            envelope_id = resp_data.get("EnvelopeID") or resp_data.get("envelope_id") or ""

            if integrator_ok:
                _logger.info("UBL send successful — UUID: %s", self.UUID)
                log_entry = (
                    f"[{fields.Datetime.now()}] Sent to GIB.\n"
                    f"  UUID       : {self.UUID}\n"
                    f"  Envelope No: {envelope_id or '—'}\n"
                    f"  Integrator : {settings.integrator_id.name if settings.integrator_id else '—'}\n"
                    f"  Test Mode  : {'Yes' if settings.test_mode else 'No'}\n"
                )
                self.write({
                    "gib_status": "sent",
                    "gib_envelope_id": envelope_id,
                    "gib_send_date": fields.Datetime.now(),
                    "gib_log": (self.gib_log or "") + log_entry,
                })
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Sent to GIB"),
                        "message": _(
                            "Invoice sent successfully.\n"
                            "UUID: %(uuid)s\n"
                            "Envelope No: %(env)s"
                        ) % {"uuid": self.UUID, "env": envelope_id or "—"},
                        "type": "success",
                        "sticky": True,
                    },
                }
            else:
                _logger.error("Integrator business error — UUID: %s — %s", self.UUID, integrator_error)
                log_entry = (
                    f"[{fields.Datetime.now()}] Integrator error.\n"
                    f"  UUID  : {self.UUID}\n"
                    f"  Error : {integrator_error}\n"
                )
                self.write({
                    "gib_status": "error",
                    "gib_response_desc": integrator_error,
                    "gib_log": (self.gib_log or "") + log_entry,
                })
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Integrator Error"),
                        "message": integrator_error,
                        "type": "danger",
                        "sticky": True,
                    },
                }
        except UserError:
            raise
        except Exception as e:
            log_entry = f"[{fields.Datetime.now()}] Send error: {str(e)}\n"
            self.write({
                "gib_status": "error",
                "gib_log": (self.gib_log or "") + log_entry,
            })
            raise UserError(_("Send error: %s") % str(e))

    def _get_xml_from_service(self):
        self.ensure_one()
        self.UUID = str(uuid_engine.uuid4())
        json_payload = self.to_json()

        # Önce aynı Odoo instance'ında doğrudan Python çağrısı dene
        xml_string = self._create_ubl_xml_direct(json_payload)
        if xml_string:
            _logger.info("UBL XML generated directly (local). UUID: %s", self.UUID)
            log_entry = (
                f"[{fields.Datetime.now()}] XML generated (local).\n"
                f"  UUID: {self.UUID}\n"
            )
            self.write({
                "gib_status": "xml_created",
                "gib_log": (self.gib_log or "") + log_entry,
            })
            return xml_string

        # Harici servis — HTTP fallback
        url = self._get_service_url().rstrip("/") + "/create_ubl_xml"
        headers = self._service_headers()
        try:
            response = requests.post(url, headers=headers, data=json.dumps(json_payload))
            if response.status_code == 200:
                _logger.info("UBL XML generated from service. UUID: %s", self.UUID)
                ubl_xml = response.json().get("ubl_xml")
                log_entry = (
                    f"[{fields.Datetime.now()}] XML generated.\n"
                    f"  UUID: {self.UUID}\n"
                )
                self.write({
                    "gib_status": "xml_created",
                    "gib_log": (self.gib_log or "") + log_entry,
                })
                return ubl_xml
            else:
                raise UserError(
                    _("UBL service returned an error while generating XML (Status: %s):\n%s")
                    % (response.status_code, response.text)
                )
        except requests.exceptions.RequestException as e:
            raise UserError(_("UBL service connection error: %s") % str(e))

    def html_to_pdf_bytes(self, html_string):
        process = subprocess.Popen(
            ["wkhtmltopdf", "-", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = process.communicate(input=html_string.encode("utf-8"))
        if process.returncode != 0:
            raise Exception(f"wkhtmltopdf error: {err.decode('utf-8')}")
        return out

    def get_pdf_data(self):
        self.ensure_one()
        xml_response = self._get_xml_from_service()
        json_payload = self.to_json()
        if not xml_response:
            raise UserError("Could not fetch XML from the service!")
        xslt_path = file_path("iber_e_transform/static/xslt/general.xslt")
        html_content = xslt2_transform(xml_response, xslt_path)
        pdf_bytes = self.html_to_pdf_bytes(html_content)
        self.xml_data = xml_response
        self.json_data = json.dumps(json_payload, indent=4, ensure_ascii=False)
        return base64.b64encode(pdf_bytes)

    def to_json(self):
        self.ensure_one()
        return {
            "Header": self.get_header(),
            "Company": self.get_company(),
            "Customer": self.get_customer(),
            "Lines": self.get_lines(),
            "Totals": self.get_total_amounts(),
            "Withholding": self.get_withholding_totals(),
            "ExtraTaxes": self.get_extra_taxes_summary(),
            "Discount": self.get_discount(),
            "Notes": self.get_invoice_notes(),
            "PaymentMeans": self.get_payment_means(),
            "PaymentTerms": self.get_payment_terms(),
            "BaseInvoicesForReturn": self.get_billing_reference(),
            "OKC": self.get_okc(),
            "SGK": self.get_sgk_info(),
        }

    @api.model
    def action_fetch_incoming_from_integrator(self, ids=None, ui_filters=None):
        """Gelen faturaları entegratörden çeker. iber_edonusum modülü bu metodu genişletir."""
        raise UserError("This action requires the 'iber_edonusum' module to be installed.")

    @api.model
    def action_sync_outgoing_from_erp(self):
        """Giden faturaları günceller. iber_edonusum veya iber_sap_b1 bu metodu genişletir."""
        return self.action_sync_from_erp()

    @api.model
    def action_sync_from_erp(self):
        """ERP sisteminden faturaları çeker. Alt modüller (iber_sap_b1 vb.) bu metodu genişletir."""
        settings = self.env["ubl21.config.settings"].get_singleton()
        if not settings:
            raise UserError("Settings not found.")
        return self._sync_from_odoo_native(settings)

    def _sync_from_odoo_native(self, settings):
        from ..erp.odoo_native_connector import OdooNativeConnector
        from ..erp.odoo_native_mapper import OdooERPMapper

        _logger.info("=== Odoo Native Invoice Sync Started ===")
        connector = OdooNativeConnector(self.env)
        mapper = OdooERPMapper(self.env)
        last_sync = settings.last_invoice_sync_datetime
        sync_start_time = fields.Datetime.now()
        created_count = 0
        updated_count = 0
        error_count = 0

        moves = connector.fetch_invoices(last_sync_datetime=last_sync)
        _logger.info("%d invoice(s) fetched from Odoo", len(moves))

        for move in moves:
            try:
                move_id_str = str(move.id)
                existing = self.search([
                    ("erp_id", "=", move_id_str),
                    ("erp_object_type", "=", mapper.get_invoice_object_type()),
                ], limit=1)
                header_vals = mapper.map_invoice_header(move)
                header_vals["erp_last_sync_date"] = fields.Datetime.now()
                if existing:
                    existing.write(header_vals)
                    self._sync_invoice_lines_from_odoo(existing, move, mapper)
                    updated_count += 1
                else:
                    new_inv = self.create(header_vals)
                    self._sync_invoice_lines_from_odoo(new_inv, move, mapper)
                    created_count += 1
            except Exception as e:
                error_count += 1
                _logger.error("Error processing invoice %s: %s", move.name, str(e))

        settings.write({"last_invoice_sync_datetime": sync_start_time})
        message = f"Sync completed.\nCreated: {created_count}\nUpdated: {updated_count}"
        if error_count:
            message += f"\nErrors: {error_count}"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Completed", "message": message, "type": "success", "sticky": False},
        }

    def _sync_invoice_lines_from_odoo(self, invoice, move, mapper):
        invoice.line_ids.unlink()
        line_commands = []
        for idx, move_line in enumerate(move.invoice_line_ids.filtered(lambda l: l.display_type == "product"), start=1):
            line_vals = mapper.map_invoice_line(move.move_type, move_line, idx)
            line_commands.append((0, 0, line_vals))
        invoice.write({"line_ids": line_commands})

    def action_view_account_move(self):
        self.ensure_one()
        if not self.account_move_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.account_move_id.id,
            "target": "current",
        }
