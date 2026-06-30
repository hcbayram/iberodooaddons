# -*- coding: utf-8 -*-
from odoo import models, fields


class EDNIntegratorHizliExt(models.Model):
    _inherit = "edn.integrator"

    hizli_secretkey = fields.Char("Secret Key (Üretim)", groups="base.group_system")
    hizli_test_secretkey = fields.Char("Secret Key (Test)", groups="base.group_system")
    hizli_token_expiry = fields.Datetime("Token Geçerlilik (Üretim)", readonly=True)
    hizli_test_token_expiry = fields.Datetime("Token Geçerlilik (Test)", readonly=True)
