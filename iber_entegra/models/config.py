from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberEntegraConfig(models.Model):
    _name = 'iber.entegra.config'
    _description = 'Entegra Bağlantı Ayarları'
    _rec_name = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    api_url = fields.Char(
        string='API URL',
        default='https://apiv2.entegrabilisim.com',
        required=True,
    )
    email = fields.Char(required=True)
    password = fields.Char()

    access_token = fields.Char(readonly=True, copy=False)
    refresh_token = fields.Char(readonly=True, copy=False)
    access_token_expiry = fields.Datetime(string='Access Token Bitiş', readonly=True, copy=False)
    refresh_token_expiry = fields.Datetime(string='Refresh Token Bitiş', readonly=True, copy=False)

    connection_state = fields.Selection([
        ('draft', 'Bağlanmadı'),
        ('connected', 'Bağlı'),
        ('error', 'Hata'),
    ], default='draft', readonly=True)
    last_error = fields.Text(readonly=True)

    last_order_sync = fields.Datetime(string='Son Sipariş Sync', readonly=True)
    last_product_sync = fields.Datetime(string='Son Ürün Sync', readonly=True)
    last_reference_sync = fields.Datetime(string='Son Referans Sync', readonly=True)

    order_ids = fields.One2many('iber.entegra.order', 'config_id')
    order_count = fields.Integer(compute='_compute_counts')

    product_mapping_ids = fields.One2many('iber.entegra.product.mapping', 'config_id')
    product_mapping_count = fields.Integer(compute='_compute_counts')

    pending_order_count = fields.Integer(compute='_compute_counts')

    @api.depends('order_ids', 'product_mapping_ids')
    def _compute_counts(self):
        for rec in self:
            rec.order_count = len(rec.order_ids)
            rec.product_mapping_count = len(rec.product_mapping_ids)
            rec.pending_order_count = len(
                rec.order_ids.filtered(lambda o: o.status in ('1', '2', '3'))
            )

    # ------------------------------------------------------------------
    # API client
    # ------------------------------------------------------------------

    def _get_client(self):
        self.ensure_one()
        from ..core.entegra_client import EntegraClient

        def _on_token_refresh(access, refresh, access_expiry, refresh_expiry):
            self.sudo().write({
                'access_token': access,
                'refresh_token': refresh,
                'access_token_expiry': access_expiry,
                'refresh_token_expiry': refresh_expiry,
                'connection_state': 'connected',
                'last_error': False,
            })

        # Odoo Datetime alanları timezone-aware olabilir; ensure_token naive UTC bekler
        def _to_naive(dt):
            if dt and hasattr(dt, 'replace'):
                return dt.replace(tzinfo=None)
            return dt

        return EntegraClient(
            email=self.email,
            password=self.password,
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            access_expiry=_to_naive(self.access_token_expiry),
            refresh_expiry=_to_naive(self.refresh_token_expiry),
            on_token_refresh=_on_token_refresh,
        )

    # ------------------------------------------------------------------
    # Aksiyonlar
    # ------------------------------------------------------------------

    def action_test_connection(self):
        self.ensure_one()
        try:
            client = self._get_client()
            client.ensure_token()
            self.write({'connection_state': 'connected', 'last_error': False})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Entegra bağlantısı başarılı.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as exc:
            self.write({'connection_state': 'error', 'last_error': str(exc)})
            raise UserError(_('Bağlantı hatası: %s') % exc)

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Siparişler'),
            'res_model': 'iber.entegra.order',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_view_product_mappings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ürün Eşleşmeleri'),
            'res_model': 'iber.entegra.product.mapping',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_open_sync_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sipariş Senkronizasyonu'),
            'res_model': 'iber.entegra.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_sync_type': 'orders',
            },
        }

    def action_open_sync_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ürün Senkronizasyonu'),
            'res_model': 'iber.entegra.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_sync_type': 'products',
            },
        }

    def action_open_sync_reference(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Referans Veri Senkronizasyonu'),
            'res_model': 'iber.entegra.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_sync_type': 'reference',
            },
        }
