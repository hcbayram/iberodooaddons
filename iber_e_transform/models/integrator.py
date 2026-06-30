from odoo import models, fields, api


class Integrator(models.Model):
    _name = "algebra.integrator"
    _description = "E-Dönüşüm Entegratör"
    _rec_name = "name"

    name = fields.Char(string="Entegratör Adı", required=True)
    code = fields.Char(string="Entegratör Kodu", required=True)
    active = fields.Boolean(string="Aktif", default=True)

    _sql_constraints = [("code_unique", "unique(code)", "Entegratör kodu benzersiz olmalıdır!")]
