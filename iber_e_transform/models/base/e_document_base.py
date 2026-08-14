import re as _re
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

GIB_ID_PATTERN = _re.compile(r'^[A-Z][A-Z0-9]{2}\d{13}$')

_logger = logging.getLogger(__name__)


class EDocumentBase(models.Model):
    _name = "algebra.base.document"
    _description = "UBL-TR Base Document"
    _xslt_path = "iber_e_transform/static/xslt/general.xslt"

    company_id = fields.Many2one(
        "res.company",
        string="Şirket",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    pdf_data = fields.Binary("PDF", readonly=True, attachment=False)
    xml_data = fields.Text("XML", readonly=True)
    json_data = fields.Text("JSON", readonly=True)

    # --- GIB / İntegratör durum bilgileri ---
    gib_status = fields.Selection(
        [
            ("draft", "Taslak"),
            ("xml_created", "XML Oluşturuldu"),
            ("sent", "GIB'e Gönderildi"),
            ("approved", "Onaylandı"),
            ("rejected", "Reddedildi"),
            ("error", "Hata"),
        ],
        string="GIB Durumu",
        default="draft",
        readonly=True,
        tracking=True,
    )
    gib_envelope_id = fields.Char("GIB Zarf No", readonly=True)
    gib_send_date = fields.Datetime("Gönderim Tarihi", readonly=True)
    gib_response_date = fields.Datetime("GIB Yanıt Tarihi", readonly=True)
    gib_response_desc = fields.Text("GIB Yanıt Açıklaması", readonly=True)
    gib_log = fields.Text("İşlem Logu", readonly=True)

    # ERP entegrasyon bilgileri
    erp_id = fields.Char("ERP ID")
    erp_object_type = fields.Char("ERP Object Type")
    erp_last_sync_date = fields.Datetime("ERP Last Sync Date")
    customer_receiver_alias = fields.Char("ERP Receiver Alias")
    branch_id = fields.Many2one(
        "algebra.base.branch",
        string="Branch/Şube",
        index=True,
        help="Şube bilgisi",
    )

    # --- header ---
    customization_id = fields.Selection(
        [("TR1.2", "TR1.2"), ("TR1.3", "TR1.3")],
        default="TR1.2",
        required=True,
    )
    profile_id = fields.Many2one("algebra.base.document.profile.id", string="Profile ID")
    profile_code = fields.Char(
        string="Profile Code",
        related="profile_id.code",
        readonly=True,
        store=True,
    )
    id_value = fields.Char(
        "Belge Numarası",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("l10n_tr.ubl.invoice") or "/",
    )
    id_value_warning = fields.Char(
        string="Numara Uyarısı",
        compute="_compute_id_value_warning",
        store=False,
    )

    @api.depends("id_value")
    def _compute_id_value_warning(self):
        # Kayıtlı prefix'leri bir kez çek (iber_edonusum kuruluysa)
        registered_prefixes = set()
        if "edn.invoice.series" in self.env:
            registered_prefixes = set(
                self.env["edn.invoice.series"].search([("active", "=", True)]).mapped("prefix")
            )

        # Gelen irsaliyelerin base_document_id'lerini bul (karşı tarafın serisi — kontrol yapılmaz)
        incoming_dn_doc_ids = set()
        if "l10n_tr.ubl.delivery.note" in self.env:
            incoming_dns = self.env["l10n_tr.ubl.delivery.note"].search([
                ("base_document_id", "in", self.ids),
                ("document_direction", "=", "incoming"),
            ])
            incoming_dn_doc_ids = set(incoming_dns.mapped("base_document_id").ids)

        for rec in self:
            # Gelen belgelerde prefix/seri kontrolü yapılmaz (karşı tarafın serisi)
            if (getattr(rec, 'invoice_direction', None) == 'incoming'
                    or rec.id in incoming_dn_doc_ids):
                rec.id_value_warning = ""
                continue

            val = (rec.id_value or "").strip()

            if not val or val == "/":
                rec.id_value_warning = "Belge numarası boş olamaz."
                continue

            # GIB formatına uyuyorsa hiçbir şey gösterme
            if GIB_ID_PATTERN.match(val):
                rec.id_value_warning = ""
                continue

            # Format uymuyor — prefix kayıtlı mı kontrol et
            prefix = val[:3].upper() if len(val) >= 3 else ""

            if registered_prefixes and prefix in registered_prefixes:
                # Prefix kayıtlı ama format tam değil — hafif uyarı
                rec.id_value_warning = (
                    f"'{val}' GIB formatına tam uymayabilir. "
                    f"Beklenen yapı: {prefix}YYYY000000000"
                )
            elif registered_prefixes and prefix not in registered_prefixes:
                # Prefix kayıtlı değil
                rec.id_value_warning = (
                    f"'{prefix}' prefixi GIB'e kayıtlı seriler arasında değil. "
                    f"Kayıtlı: {', '.join(sorted(registered_prefixes))}"
                )
            else:
                # iber_edonusum kurulu değil — sadece bilgi
                rec.id_value_warning = (
                    f"GIB formatına uymuyor (beklenen: 3 harf + 4 yıl + 9 rakam). "
                    f"Mevcut: '{val}'"
                )
    issue_date = fields.Date("Issue Date", default=fields.Date.context_today, required=True)
    document_type_id = fields.Many2one("algebra.base.document.type", string="Document Type")
    document_type_code = fields.Char(string="Document Type Code", related="document_type_id.code")
    document_currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.ref("base.TRY", raise_if_not_found=False),
    )
    document_exchange_rate = fields.Float("Exchange Rate", default=1.0)
    UUID = fields.Char("UUID Number of E-Invoice", readonly=True)

    # --- inline parties (supplier) ---
    supplier_name = fields.Char("Gönderici Adı", required=True)
    supplier_vkn_tckn = fields.Char("VKN/TCKN")
    supplier_tax_office = fields.Char("Vergi Dairesi")
    supplier_pname = fields.Char("Şahıs Adı")
    supplier_psurname = fields.Char("Şahıs Soyadı")
    supplier_scheme_id = fields.Selection([("VKN", "VKN"), ("TCKN", "TCKN")])
    supplier_street = fields.Char("Adres")
    supplier_county = fields.Char("İlçe")
    supplier_city = fields.Char("İl")
    supplier_postal_code = fields.Char("Posta Kodu")
    supplier_country_code = fields.Char(string="Country Code", default="TR")
    supplier_country_name = fields.Char(string="Country Name", default="TÜRKİYE")

    # --- inline parties (customer) ---
    customer_card_code = fields.Char("ERP Card Code")
    customer_name = fields.Char("Alıcı Adı", required=True)
    customer_vkn_tckn = fields.Char("VKN/TCKN")
    customer_tax_office = fields.Char("Vergi Dairesi")
    customer_pname = fields.Char("Şahıs Adı")
    customer_psurname = fields.Char("Şahıs Soyadı")
    customer_scheme_id = fields.Selection([("VKN", "VKN"), ("TCKN", "TCKN")])
    customer_street = fields.Char("Adres")
    customer_county = fields.Char("İlçe")
    customer_city = fields.Char("İl")
    customer_postal_code = fields.Char("Posta Kodu")
    customer_country_code = fields.Char(string="Country Code", default="TR")
    customer_country_name = fields.Char(string="Country Name", default="TÜRKİYE")

    line_ids = fields.One2many("algebra.base.document.line", "base_document_id", string="Lines")
    invoice_note_ids = fields.One2many(
        "algebra.base.document.note",
        "base_document_id",
        string="Invoice Notes",
    )
    supplier_extra_ids = fields.One2many(
        "algebra.base.document.supplier.extra.id",
        "base_document_id",
        string="Supplier Identifications",
    )
    customer_extra_ids = fields.One2many(
        "algebra.base.document.customer.extra.id",
        "base_document_id",
        string="Customer Identifications",
    )
    order_id = fields.Char("Order ID")
    order_issue_date = fields.Date("Order Issue Date")

    def _get_profile_id_domain(self):
        raise NotImplementedError("Belge türüne göre implement edilmeli.")

    def action_send_to_ubl_service(self):
        raise NotImplementedError("Belge türüne göre implement edilmeli.")

    def action_preview_pdf(self):
        raise NotImplementedError("Belge türüne göre implement edilmeli.")

    def action_clear_pdf_preview(self):
        raise NotImplementedError("Belge türüne göre implement edilmeli.")

    def _get_service_url(self):
        raise NotImplementedError("Belge türüne göre implement edilmeli.")


class BaseDocumentSupplierExtraIDs(models.Model):
    _name = "algebra.base.document.supplier.extra.id"
    _description = "Supplier Extra Identification"

    base_document_id = fields.Many2one(
        "algebra.base.document", string="Base Document", required=True, ondelete="cascade"
    )
    type_id = fields.Many2one("l10n_tr.ubl.partyid.type", string="Type", required=True)
    value = fields.Char("Value", required=True)


class BaseDocumentCustomerExtraIDs(models.Model):
    _name = "algebra.base.document.customer.extra.id"
    _description = "Customer Extra Identification"

    base_document_id = fields.Many2one(
        "algebra.base.document", string="Base Document", required=True, ondelete="cascade"
    )
    type_id = fields.Many2one("l10n_tr.ubl.partyid.type", string="Type", required=True)
    value = fields.Char("Value", required=True)


class BaseDocumentProfileId(models.Model):
    _name = "algebra.base.document.profile.id"
    _description = "UBL-TR Document Profile ID"

    code = fields.Char("Code", required=True, index=True)
    name = fields.Char("Name", required=True)
    profile_type = fields.Selection(
        [
            ("invoice", "Invoice"),
            ("receipt", "Receipt"),
            ("delivery_note", "Delivery Note"),
        ],
        string="Document Type",
        required=True,
        default="invoice",
    )
    _sql_constraints = [("code_unique", "unique(code)", "Profile ID code must be unique.")]


class BaseDocumentType(models.Model):
    _name = "algebra.base.document.type"
    _description = "UBL-TR Document Type"

    code = fields.Char("Code", required=True, index=True)
    name = fields.Char("Name", required=True)
    doc_type = fields.Selection(
        [
            ("invoice", "Invoice"),
            ("credit_note", "Credit Note"),
            ("receipt", "Receipt"),
            ("delivery_note", "Delivery Note"),
        ],
        string="Document Type",
        required=True,
        default="invoice",
    )
    _sql_constraints = [("code_unique", "unique(code)", "Invoice Type code must be unique.")]


class BaseDocumentNote(models.Model):
    _name = "algebra.base.document.note"
    _description = "UBL Document Notes"
    _order = "sequence,id"

    base_document_id = fields.Many2one(
        "algebra.base.document", string="Base Document", ondelete="cascade", required=True
    )
    sequence = fields.Integer(default=10)
    note = fields.Text("Note", required=True)
