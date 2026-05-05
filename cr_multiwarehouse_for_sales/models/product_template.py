# -*- coding: utf-8 -*-
# Part of Creyox technologies.

from odoo import fields, models, api


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sale_warehouse_id = fields.Many2one("stock.warehouse", string="Sale Warehouse")
