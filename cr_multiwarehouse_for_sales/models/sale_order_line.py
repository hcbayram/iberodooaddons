# -*- coding: utf-8 -*-
# Part of Creyox technologies.

from odoo import models, fields, api, _


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    warehouses_id = fields.Many2one("stock.warehouse", string="Warehouse")
    is_sale_warehouse = fields.Boolean()

    @api.onchange("product_id")
    def _set_required_warehouse(self):
        company = self.env.company
        self.is_sale_warehouse = company.allow_sale_warehouse
        if self.product_id:
            self.warehouses_id = self.product_id.sale_warehouse_id.id

    def _prepare_procurement_values(self):
        res = super(SaleOrderLine, self)._prepare_procurement_values()

        res_config = self.env.company
        if res_config.allow_sale_warehouse:
            res.update({"warehouse_id": self.warehouses_id})

        return res
