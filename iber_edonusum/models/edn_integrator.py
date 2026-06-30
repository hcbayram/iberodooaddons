# -*- coding: utf-8 -*-
from odoo import models, fields, api


class EDNIntegrator(models.Model):
    _name = "edn.integrator"
    _description = "E-Dönüşüm Entegratörü"
    _rec_name = "name"

    name = fields.Char("Entegratör Adı", required=True)
    code = fields.Char(
        "Kod",
        required=True,
        help="Factory tarafından kullanılan entegratör kodu (NES, UYUMSOFT, FORIBA vb.)",
    )
    module_name = fields.Char(
        "Addon Adı",
        help="Bu entegratörü sağlayan Odoo addon adı (örn. iber_edonusum_nes)",
    )
    active = fields.Boolean("Aktif", default=True)

    is_test = fields.Boolean(
        "Test Ortamı Aktif",
        default=True,
        help="Etkin olduğunda test credential'ları kullanılır; kapalıysa üretim credential'ları kullanılır.",
    )

    # Üretim bağlantı bilgileri
    base_url = fields.Char("API URL (Üretim)")
    username = fields.Char("Kullanıcı Adı (Üretim)")
    password = fields.Char("Şifre (Üretim)")
    apikey = fields.Char("API Key (Üretim)")
    token = fields.Char("Token (Üretim)", help="Login sonrası Bearer token — otomatik doldurulur")

    # Test bağlantı bilgileri
    test_base_url = fields.Char("API URL (Test)")
    test_username = fields.Char("Kullanıcı Adı (Test)")
    test_password = fields.Char("Şifre (Test)")
    test_apikey = fields.Char("API Key (Test)")
    test_token = fields.Char("Token (Test)", help="Login sonrası Bearer token — otomatik doldurulur")

    extra = fields.Text(
        "Ek Parametreler (JSON)",
        help='Entegratöre özgü alanlar: secretkey, token_expiry, test_secretkey, test_token_expiry vb.\nÖrn: {"secretkey": "abc", "token_expiry": "2026-06-30T10:00:00"}',
    )

    series_ids = fields.One2many(
        "edn.invoice.series",
        "integrator_id",
        string="Kayıtlı Seriler",
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "Entegratör kodu benzersiz olmalıdır!")
    ]

    def action_fetch_series(self):
        self.ensure_one()
        result = self.env["edn.document.manager"].fetch_and_sync_series(self.code)
        if result.get("ok"):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Seriler Güncellendi",
                    "message": f"{result['synced']} seri kodu senkronize edildi.",
                    "type": "success",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Kısmi Hata",
                "message": result.get("error", "Bilinmeyen hata"),
                "type": "warning",
                "sticky": True,
            },
        }
