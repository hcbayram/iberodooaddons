# -*- coding: utf-8 -*-
from odoo import models, fields, api


class EDNIntegrator(models.Model):
    _name = "edn.integrator"
    _description = "e-Transformation Integrator"
    _rec_name = "name"

    name = fields.Char("Integrator Name", required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    code = fields.Char(
        "Code",
        required=True,
        help="Integrator code used by the factory (NES, UYUMSOFT, FORIBA, etc.)",
    )
    module_name = fields.Char(
        "Addon Name",
        help="Name of the System addon that provides this integrator (e.g. iber_edonusum_nes)",
    )
    active = fields.Boolean("Active", default=True)

    is_test = fields.Boolean(
        "Test Environment Active",
        default=True,
        help="When enabled, test credentials are used; when disabled, production credentials are used.",
    )

    # Üretim bağlantı bilgileri
    base_url = fields.Char("API URL (Production)")
    username = fields.Char("Username (Production)")
    password = fields.Char("Password (Production)")
    apikey = fields.Char("API Key (Production)")
    token = fields.Char("Token (Production)", help="Bearer token after login — filled automatically")

    # Test bağlantı bilgileri
    test_base_url = fields.Char("API URL (Test)")
    test_username = fields.Char("Username (Test)")
    test_password = fields.Char("Password (Test)")
    test_apikey = fields.Char("API Key (Test)")
    test_token = fields.Char("Token (Test)", help="Bearer token after login — filled automatically")

    extra = fields.Text(
        "Additional Parameters (JSON)",
        help='Integrator-specific fields: secretkey, token_expiry, test_secretkey, test_token_expiry, etc.\nE.g.: {"secretkey": "abc", "token_expiry": "2026-06-30T10:00:00"}',
    )

    series_ids = fields.One2many(
        "edn.invoice.series",
        "integrator_id",
        string="Registered Series",
    )

    _sql_constraints = [
        ("code_company_unique", "unique(code, company_id)",
         "Only 1 record can exist per company for this integrator code!")
    ]

    def action_fetch_series(self):
        self.ensure_one()
        result = self.env["edn.document.manager"].fetch_and_sync_series(self.code)
        if result.get("ok"):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Series Updated",
                    "message": f"{result['synced']} series code(s) synced.",
                    "type": "success",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Partial Error",
                "message": result.get("error", "Unknown error"),
                "type": "warning",
                "sticky": True,
            },
        }
