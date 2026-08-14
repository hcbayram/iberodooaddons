from odoo import models, fields, api


class UBL21ConfigSettings(models.Model):
    _name = "ubl21.config.settings"
    _description = "UBL-TR 2.1 Settings"
    _rec_name = "name"

    name = fields.Char(default="UBL 2.1 Ayarları", readonly=True)
    company_id = fields.Many2one(
        "res.company",
        string="Şirket",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    # === AKTİF ERP SEÇİMİ ===
    # Not: iber_sap_b1 gibi ek modüller bu listeye kendi seçeneklerini ekler
    active_erp = fields.Selection(
        [
            ("odoo_native", "Odoo 19 Enterprise (Yerleşik)"),
            ("other", "Diğer ERP"),
        ],
        string="Aktif ERP",
        default="odoo_native",
        required=True,
        help="E-dönüşüm belgelerinin kaynağı olan ERP sistemi",
    )

    # === GENEL AYARLAR ===
    ubl_service_url = fields.Char(
        string="UBL Servis URL",
        default="http://localhost:8019/algebra_service_layer/",
        help="UBL XML oluşturma ve gönderme servisi URL adresi",
    )
    erp_company_name = fields.Char(string="Şirket Adı")
    erp_vkn_tckn = fields.Char(string="VKN/TCKN")
    erp_tax_office = fields.Char(string="Vergi Dairesi")
    erp_street = fields.Char(string="Adres")
    erp_county = fields.Char(string="İlçe")
    erp_city = fields.Char(string="İl")
    erp_country_code = fields.Char(string="Ülke Kodu", default="TR")
    erp_country_name = fields.Char(string="Ülke Adı", default="TÜRKİYE")
    erp_postal_code = fields.Char(string="Posta Kodu")
    erp_pname = fields.Char(string="Şahıs Adı")
    erp_psurname = fields.Char(string="Şahıs Soyadı")
    erp_sender_alias = fields.Char(
        string="Gönderici Alias",
        default="urn:mail:defaultgb@nes.com.tr",
    )

    # === ERP SYNC TARİH BİLGİSİ ===
    last_invoice_sync_datetime = fields.Datetime(
        string="Son Fatura Senkronizasyon Zamanı", readonly=True
    )
    last_delivery_note_sync_datetime = fields.Datetime(
        string="Son İrsaliye Senkronizasyon Zamanı", readonly=True
    )


    _sql_constraints = [
        # Singleton enforcement: şirket başına en fazla 1 kayıt olabilir
        ("company_uniq", "unique(company_id)", "Şirket başına yalnızca 1 ayar kaydı olabilir!"),
    ]

    @api.model
    def get_singleton(self):
        """Mevcut şirketin tek ayar kaydını döner, yoksa oluşturur."""
        company = self.env.company
        rec = self.sudo().search([("company_id", "=", company.id)], limit=1, order="id asc")
        if not rec:
            rec = self.sudo().create({"name": "UBL 2.1 Ayarları", "company_id": company.id})
        return rec

    @api.model_create_multi
    def create(self, vals_list):
        """Singleton: şirket başına yalnızca 1 kayıt olmasını garanti eder."""
        results = self.browse()
        for vals in vals_list:
            company_id = vals.get("company_id") or self.env.company.id
            existing = self.sudo().search([("company_id", "=", company_id)], limit=1)
            if existing:
                # Bu şirket için zaten bir kayıt var → oluşturma, var olanı döndür
                results |= existing
            else:
                vals.setdefault("company_id", company_id)
                results |= super(UBL21ConfigSettings, self).create([vals])
        return results

    @api.model
    def action_open_settings(self):
        """Singleton formu her zaman mevcut kaydı açar."""
        rec = self.get_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": "E-Dönüşüm Ayarları",
            "res_model": "ubl21.config.settings",
            "view_mode": "form",
            "res_id": rec.id,
            "target": "current",
            "flags": {"mode": "edit"},
        }

    def action_save(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Başarılı", "message": "Ayarlar kaydedildi.", "type": "success", "sticky": False},
        }

    def action_clear_invoice_sync_time(self):
        self.ensure_one()
        self.write({"last_invoice_sync_datetime": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Başarılı", "message": "Fatura senkronizasyon zamanı temizlendi.", "type": "success", "sticky": False},
        }

    def action_clear_delivery_note_sync_time(self):
        self.ensure_one()
        self.write({"last_delivery_note_sync_datetime": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Başarılı", "message": "İrsaliye senkronizasyon zamanı temizlendi.", "type": "success", "sticky": False},
        }
