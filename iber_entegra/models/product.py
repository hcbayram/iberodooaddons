from odoo import models, fields, api, _


class IberEntegraProduct(models.Model):
    _name = 'iber.entegra.product'
    _description = 'Entegra Ürün (Staging)'
    _rec_name = 'name'
    _order = 'name'

    config_id = fields.Many2one(
        'iber.entegra.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True)

    # --- Entegra alanları ---
    entegra_id = fields.Integer(string='Entegra ID', index=True, readonly=True)
    product_code = fields.Char(string='Ürün Kodu', index=True, readonly=True)
    name = fields.Char(string='Ürün Adı', readonly=True)
    barcode = fields.Char(string='Barkod', readonly=True)
    brand = fields.Char(string='Marka', readonly=True)
    status = fields.Char(string='Durum', readonly=True)
    quantity = fields.Float(string='Stok', readonly=True)
    price1 = fields.Float(string='Fiyat 1', readonly=True)
    price2 = fields.Float(string='Fiyat 2', readonly=True)
    kdv_id = fields.Char(string='KDV %', readonly=True)
    supplier = fields.Char(string='Pazaryeri', readonly=True)
    last_sync = fields.Datetime(string='Son Sync', readonly=True)

    # --- Odoo eşleşmesi ---
    mapping_id = fields.Many2one(
        'iber.entegra.product.mapping',
        string='Odoo Eşleşmesi',
        compute='_compute_mapping',
        store=True,
    )
    odoo_product_id = fields.Many2one(
        'product.template',
        related='mapping_id.product_tmpl_id',
        string='Odoo Ürünü',
        readonly=True,
    )

    _sql_constraints = [
        ('unique_config_code',
         'unique(config_id, product_code)',
         'Bu bağlantı için aynı ürün kodu zaten mevcut.'),
    ]

    @api.depends('product_code', 'config_id')
    def _compute_mapping(self):
        Mapping = self.env['iber.entegra.product.mapping']
        for rec in self:
            if rec.product_code and rec.config_id:
                rec.mapping_id = Mapping.search([
                    ('config_id', '=', rec.config_id.id),
                    ('entegra_product_code', '=', rec.product_code),
                ], limit=1)
            else:
                rec.mapping_id = False

    def action_create_mapping(self):
        """Seçili Entegra ürünü için product.mapping wizard açar."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Odoo Ürünü Eşleştir'),
            'res_model': 'iber.entegra.product.mapping',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.config_id.id,
                'default_entegra_product_code': self.product_code,
                'default_entegra_barcode': self.barcode,
                'default_entegra_product_id': self.entegra_id,
            },
        }
