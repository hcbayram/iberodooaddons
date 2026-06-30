from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberTicimaxConfig(models.Model):
    _name = 'iber.ticimax.config'
    _description = 'Ticimax Bağlantı Ayarları'
    _rec_name = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    base_url = fields.Char(
        string='Site URL',
        help='Örn: https://www.siteadi.com',
        required=True,
    )
    uye_kodu = fields.Char(
        string='Üye Kodu (API Şifresi)',
        required=True,
    )
    timeout = fields.Integer(string='Zaman Aşımı (sn)', default=30)

    connection_state = fields.Selection([
        ('draft', 'Bağlanmadı'),
        ('connected', 'Bağlı'),
        ('error', 'Hata'),
    ], default='draft', readonly=True)
    last_error = fields.Text(string='Son Hata', readonly=True)

    last_category_sync = fields.Datetime(string='Son Kategori Sync', readonly=True)
    last_brand_sync = fields.Datetime(string='Son Marka Sync', readonly=True)
    last_order_sync = fields.Datetime(string='Son Sipariş Sync', readonly=True)
    last_product_sync = fields.Datetime(string='Son Ürün Sync', readonly=True)

    category_ids = fields.One2many('iber.ticimax.category', 'config_id', string='Kategoriler')
    brand_ids = fields.One2many('iber.ticimax.brand', 'config_id', string='Markalar')
    order_ids = fields.One2many('iber.ticimax.order', 'config_id', string='Siparişler')
    product_ids = fields.One2many('iber.ticimax.product', 'config_id', string='Ürünler')

    category_count = fields.Integer(compute='_compute_counts')
    brand_count = fields.Integer(compute='_compute_counts')
    order_count = fields.Integer(compute='_compute_counts')
    product_count = fields.Integer(compute='_compute_counts')
    pending_order_count = fields.Integer(compute='_compute_counts')

    @api.depends('category_ids', 'brand_ids', 'order_ids', 'product_ids')
    def _compute_counts(self):
        for rec in self:
            rec.category_count = len(rec.category_ids)
            rec.brand_count = len(rec.brand_ids)
            rec.order_count = len(rec.order_ids)
            rec.product_count = len(rec.product_ids)
            rec.pending_order_count = len(
                rec.order_ids.filtered(lambda o: o.siparis_durumu in ('1', '2', '3', '4', '5'))
            )

    # ------------------------------------------------------------------
    # API client
    # ------------------------------------------------------------------

    def _get_client(self):
        self.ensure_one()
        from ..core.ticimax_client import TicimaxClient
        return TicimaxClient(
            base_url=self.base_url,
            uye_kodu=self.uye_kodu,
            timeout=self.timeout or 30,
        )

    # ------------------------------------------------------------------
    # Aksiyonlar
    # ------------------------------------------------------------------

    def action_test_connection(self):
        self.ensure_one()
        try:
            client = self._get_client()
            # SelectKategori(0) bağlantıyı doğrular
            client.select_kategori(0)
            self.write({'connection_state': 'connected', 'last_error': False})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Ticimax bağlantısı başarılı.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as exc:
            self.write({'connection_state': 'error', 'last_error': str(exc)})
            raise UserError(_('Bağlantı hatası: %s') % exc)

    def action_view_categories(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Kategoriler'),
            'res_model': 'iber.ticimax.category',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_view_brands(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Markalar'),
            'res_model': 'iber.ticimax.brand',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Siparişler'),
            'res_model': 'iber.ticimax.order',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ürünler'),
            'res_model': 'iber.ticimax.product',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_open_sync(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Senkronizasyon'),
            'res_model': 'iber.ticimax.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_config_id': self.id},
        }
