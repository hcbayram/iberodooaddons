# -*- coding: utf-8 -*-
from odoo import models


class EDNDocumentManagerHizliExt(models.Model):
    _inherit = "edn.document.manager"

    def _make_settings(self, integ):
        settings = super()._make_settings(integ)
        if integ.code != "HIZLI":
            return settings
        if settings["is_test"]:
            settings["secretkey"] = integ.hizli_test_secretkey or ""
            settings["token_expiry"] = integ.hizli_test_token_expiry
        else:
            settings["secretkey"] = integ.hizli_secretkey or ""
            settings["token_expiry"] = integ.hizli_token_expiry
        return settings
