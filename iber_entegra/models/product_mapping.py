from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberEntegraProductMapping(models.Model):
    _name = 'iber.entegra.product.mapping'
    _description = 'Entegra Ürün Eşleşmesi'
    _rec_name = 'entegra_product_code'

    config_id = fields.Many2one(
        'iber.entegra.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True)

    product_tmpl_id = fields.Many2one(
        'product.template', string='Odoo Ürünü', required=True)
    product_id = fields.Many2one(
        'product.product', string='Odoo Varyantı',
        domain="[('product_tmpl_id', '=', product_tmpl_id)]")

    entegra_product_code = fields.Char(string='Entegra Ürün Kodu', required=True)
    entegra_barcode = fields.Char(string='Entegra Barkod')
    entegra_product_id = fields.Integer(string='Entegra ID')

    sync_prices = fields.Boolean(string='Fiyat Senkronize Et', default=True)
    sync_quantities = fields.Boolean(string='Stok Senkronize Et', default=True)

    last_price_sync = fields.Datetime(string='Son Fiyat Sync', readonly=True)
    last_qty_sync = fields.Datetime(string='Son Stok Sync', readonly=True)

    state = fields.Selection([
        ('active', 'Aktif'),
        ('error', 'Hata'),
        ('inactive', 'Pasif'),
    ], default='active')
    last_error = fields.Text(string='Son Hata', readonly=True)

    _sql_constraints = [
        ('unique_config_product_code',
         'unique(config_id, entegra_product_code)',
         'Bu bağlantı için aynı Entegra ürün kodu zaten mevcut.'),
    ]

    def _effective_product(self):
        self.ensure_one()
        return self.product_id or self.product_tmpl_id.product_variant_id

    def action_push_price(self):
        for rec in self:
            try:
                client = rec.config_id._get_client()
                price = rec._effective_product().list_price
                # PUT /product/ — genel güncelleme (price1: ana fiyat)
                payload = {'list': [{'productCode': rec.entegra_product_code, 'price1': price}]}
                client.update_product(payload)
                rec.write({
                    'last_price_sync': fields.Datetime.now(),
                    'last_error': False,
                    'state': 'active',
                })
            except Exception as exc:
                rec.write({'state': 'error', 'last_error': str(exc)})
                raise UserError(_('Fiyat güncellenirken hata (%s): %s') % (rec.entegra_product_code, exc))

    def action_push_quantity(self):
        for rec in self:
            try:
                client = rec.config_id._get_client()
                qty = int(rec._effective_product().qty_available)
                # PUT /product/quantity/ — stok güncelleme
                payload = {'list': [{
                    'productCode': rec.entegra_product_code,
                    'store_id': 0,
                    'quantity': qty,
                }]}
                client.update_product_quantity(payload)
                rec.write({
                    'last_qty_sync': fields.Datetime.now(),
                    'last_error': False,
                    'state': 'active',
                })
            except Exception as exc:
                rec.write({'state': 'error', 'last_error': str(exc)})
                raise UserError(_('Stok güncellenirken hata (%s): %s') % (rec.entegra_product_code, exc))
