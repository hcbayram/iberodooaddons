# -*- coding: utf-8 -*-
# Part of Creyox technologies.

from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = "res.company"

    allow_sale_warehouse = fields.Boolean(
        string="Allow Warehouse in Sale Order Line", default=False
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    allow_sale_warehouse = fields.Boolean(
        string="Allow Warehouse in Sale Order Line",
        related="company_id.allow_sale_warehouse",
        readonly=False,
    )
