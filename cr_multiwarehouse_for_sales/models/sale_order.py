# -*- coding: utf-8 -*-
# Part of Creyox technologies.

from odoo import models, fields
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_multi_warehouse = fields.Boolean(string="Multi Warehouse", default=False)

    def _action_confirm(self):
        super(SaleOrder, self)._action_confirm()
