# -*- coding: utf-8 -*-
from odoo import models, fields, api


class UBL21ConfigSettingsIntegratorExt(models.Model):
    _inherit = "ubl21.config.settings"

    integrator_id = fields.Many2one(
        "edn.integrator",
        string="Aktif Entegratör",
        help="Bağlantı bilgileri ve test/üretim ortamı entegratör kaydından okunur.",
    )

    @api.model
    def action_install_integrator(self):
        """Kurulabilir entegratör addon'larını filtreli listeler."""
        return {
            "type": "ir.actions.act_window",
            "name": "Entegratör Kur",
            "res_model": "ir.module.module",
            "view_mode": "list,form",
            "domain": [("name", "like", "iber_edonusum_"), ("name", "!=", "iber_edonusum")],
        }
