from odoo import models, fields


class IberEntegraCategory(models.Model):
    _name = 'iber.entegra.category'
    _description = 'Entegra Kategorisi'
    _order = 'name'
    _rec_name = 'name'

    entegra_id = fields.Integer(string='Entegra ID', index=True)
    name = fields.Char(required=True)
    parent_id = fields.Many2one('iber.entegra.category', string='Üst Kategori', ondelete='set null')
    child_ids = fields.One2many('iber.entegra.category', 'parent_id', string='Alt Kategoriler')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
