from odoo import models, fields
from ..core.entegra_const import MARKETPLACE_CODES


class IberEntegraStore(models.Model):
    _name = 'iber.entegra.store'
    _description = 'Entegra Mağazası'
    _order = 'name'
    _rec_name = 'name'

    config_id = fields.Many2one('iber.entegra.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True)

    entegra_id = fields.Integer(string='Entegra ID', index=True)
    name = fields.Char(required=True)
    marketplace = fields.Selection(MARKETPLACE_CODES, string='Pazaryeri')
    active = fields.Boolean(default=True)
