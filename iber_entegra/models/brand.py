from odoo import models, fields


class IberEntegraaBrand(models.Model):
    _name = 'iber.entegra.brand'
    _description = 'Entegra Markası'
    _order = 'name'
    _rec_name = 'name'

    entegra_id = fields.Integer(string='Entegra ID', index=True)
    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
