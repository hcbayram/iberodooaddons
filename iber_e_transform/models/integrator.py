from odoo import models, fields, api


class Integrator(models.Model):
    _name = "algebra.integrator"
    _description = "e-Transformation Integrator"
    _rec_name = "name"

    name = fields.Char(string="Integrator Name", required=True)
    code = fields.Char(string="Integrator Code", required=True)
    active = fields.Boolean(string="Active", default=True)

    _sql_constraints = [("code_unique", "unique(code)", "Integrator code must be unique!")]
