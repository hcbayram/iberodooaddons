from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..core.trendyol_const import CARGO_COMPANIES


class IberTrendyolConfig(models.Model):
    _name = 'iber.marketplace.trendyol.config'
    _description = 'Trendyol Bağlantı Ayarları'
    _rec_name = 'name'

    name = fields.Char(required=True, string='Ad')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        string='Şirket')
    active = fields.Boolean(default=True)

    # Trendyol kimlik bilgileri
    merchant_id = fields.Char(
        required=True, string='Tedarikçi ID',
        help='Trendyol Tedarikçi (Merchant) ID numarası')
    api_key = fields.Char(required=True, string='API Key')
    api_secret = fields.Char(required=True, string='API Secret', password=True)
    webhook_token = fields.Char(string='Webhook Token', copy=False,
                                help='Trendyol webhook doğrulama tokeni')

    # Varsayılan kargo şirketi
    cargo_provider_name = fields.Selection(
        selection=CARGO_COMPANIES,
        string='Varsayılan Kargo Şirketi',
        help='Kargo bilgisi gönderilirken kullanılacak varsayılan kargo şirketi',
    )

    # Bağlantı durumu
    connection_state = fields.Selection([
        ('draft', 'Bağlanmadı'),
        ('connected', 'Bağlı'),
        ('error', 'Hata'),
    ], default='draft', readonly=True, string='Bağlantı Durumu')
    last_error = fields.Text(readonly=True, string='Son Hata')

    # Senkronizasyon bilgisi
    last_order_sync = fields.Datetime(readonly=True, string='Son Sipariş Sync')
    last_inventory_sync = fields.Datetime(readonly=True, string='Son Stok Sync')

    # İlişkili kayıtlar
    order_ids = fields.One2many(
        'iber.marketplace.trendyol.order', 'config_id', string='Siparişler')
    order_count = fields.Integer(compute='_compute_counts', string='Sipariş')
    pending_order_count = fields.Integer(compute='_compute_counts', string='Bekleyen')

    listing_ids = fields.One2many(
        'iber.marketplace.trendyol.listing', 'config_id', string='Ürün Listesi')
    listing_count = fields.Integer(compute='_compute_counts', string='Ürün')

    # ------------------------------------------------------------------
    # Hesaplanan alanlar
    # ------------------------------------------------------------------

    @api.depends('order_ids', 'order_ids.status', 'listing_ids')
    def _compute_counts(self):
        pending_statuses = ('Created', 'Picking', 'Invoiced')
        for rec in self:
            rec.order_count = len(rec.order_ids)
            rec.pending_order_count = len(
                rec.order_ids.filtered(lambda o: o.status in pending_statuses)
            )
            rec.listing_count = len(rec.listing_ids)

    # ------------------------------------------------------------------
    # Hub senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_hub_channel(self):
        """Kaydedilen config'i hub'daki iber.marketplace.channel ile senkronize et."""
        Channel = self.env.get('iber.marketplace.channel')
        if not Channel:
            return
        for rec in self:
            Channel._sync_from_config('trendyol', rec)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_hub_channel()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._sync_hub_channel()
        return result

    # ------------------------------------------------------------------
    # API istemcisi
    # ------------------------------------------------------------------

    def _get_client(self):
        self.ensure_one()
        from ..core.trendyol_client import TrendyolClient
        return TrendyolClient(
            merchant_id=self.merchant_id,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

    # ------------------------------------------------------------------
    # Aksiyonlar — manuel
    # ------------------------------------------------------------------

    def action_test_connection(self):
        self.ensure_one()
        try:
            client = self._get_client()
            client.get_orders(page=0, size=1)
            self.write({'connection_state': 'connected', 'last_error': False})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Trendyol bağlantısı başarılı.'),
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
            'res_model': 'iber.marketplace.trendyol.order',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_view_listings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ürün Listesi'),
            'res_model': 'iber.marketplace.trendyol.listing',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_open_sync_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Senkronizasyon'),
            'res_model': 'iber.marketplace.trendyol.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
            },
        }

    # ------------------------------------------------------------------
    # Aksiyonlar — cron
    # ------------------------------------------------------------------

    def action_cron_sync_orders(self):
        """Cron: tüm aktif konfigürasyonlar için sipariş senkronizasyonu."""
        configs = self.search([('active', '=', True)])
        for cfg in configs:
            try:
                wizard = self.env['iber.marketplace.trendyol.sync.wizard'].create({
                    'config_id': cfg.id,
                    'sync_type': 'orders',
                    'order_days_back': 7 if not cfg.last_order_sync else 2,
                })
                wizard._sync_orders()
            except Exception as exc:
                cfg.write({
                    'connection_state': 'error',
                    'last_error': str(exc),
                })

    def action_cron_sync_inventory(self):
        """Cron: tüm aktif konfigürasyonlar için stok senkronizasyonu."""
        configs = self.search([('active', '=', True)])
        for cfg in configs:
            try:
                listings = self.env['iber.marketplace.trendyol.listing'].search([
                    ('config_id', '=', cfg.id),
                    ('active', '=', True),
                ])
                if listings:
                    listings.action_push_inventory()
                    cfg.write({'last_inventory_sync': fields.Datetime.now()})
            except Exception as exc:
                cfg.write({
                    'connection_state': 'error',
                    'last_error': str(exc),
                })
