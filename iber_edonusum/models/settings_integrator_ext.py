# -*- coding: utf-8 -*-
from odoo import models, fields


class UBL21ConfigSettingsIntegratorExt(models.Model):
    _inherit = "ubl21.config.settings"

    integrator_id = fields.Many2one(
        "edn.integrator",
        string="Active Integrator",
        help="Connection details and test/production environment are read from the integrator record.",
    )

    def action_install_integrator(self):
        """Kurulabilir entegratör addon'larını filtreli listeler."""
        return {
            "type": "ir.actions.act_window",
            "name": "Install Integrator",
            "res_model": "ir.module.module",
            "view_mode": "list,form",
            "domain": [("name", "like", "iber_edonusum_"), ("name", "!=", "iber_edonusum")],
        }
