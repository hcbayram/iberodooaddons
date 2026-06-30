from odoo import models, fields, api, _
from odoo.exceptions import UserError

CHANNEL_TYPES = [
    ('trendyol', 'Trendyol'),
    ('hepsiburada', 'Hepsiburada'),
    ('n11', 'N11'),
    ('pttavm', 'PttAVM'),
    ('ciceksepeti', 'Çiçeksepeti'),
    ('pazarama', 'Pazarama'),
    ('amazon', 'Amazon TR'),
]

# connector model adı: (config_model, order_model, listing_model)
_CONNECTOR_MODELS = {
    'trendyol': (
        'iber.marketplace.trendyol.config',
        'iber.marketplace.trendyol.order',
        'iber.marketplace.trendyol.listing',
    ),
    'hepsiburada': (
        'iber.marketplace.hepsiburada.config',
        'iber.marketplace.hepsiburada.order',
        'iber.marketplace.hepsiburada.listing',
    ),
    'pttavm': (
        'iber.marketplace.pttavm.config',
        'iber.marketplace.pttavm.order',
        'iber.marketplace.pttavm.listing',
    ),
    'n11': (
        'iber.marketplace.n11.config',
        'iber.marketplace.n11.order',
        'iber.marketplace.n11.listing',
    ),
    'ciceksepeti': (
        'iber.marketplace.ciceksepeti.config',
        'iber.marketplace.ciceksepeti.order',
        'iber.marketplace.ciceksepeti.listing',
    ),
    'pazarama': (
        'iber.marketplace.pazarama.config',
        'iber.marketplace.pazarama.order',
        'iber.marketplace.pazarama.listing',
    ),
    'amazon': (
        'iber.marketplace.amazon.config',
        'iber.marketplace.amazon.order',
        'iber.marketplace.amazon.listing',
    ),
}


class IberMarketplaceChannel(models.Model):
    _name = 'iber.marketplace.channel'
    _description = 'Pazaryeri Kanalı'
    _order = 'channel_type, name'
    _rec_name = 'name'

    name = fields.Char(required=True, string='Mağaza Adı')
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company, string='Şirket')
    active = fields.Boolean(default=True)
    channel_type = fields.Selection(
        selection=CHANNEL_TYPES, required=True, string='Pazaryeri')
    color = fields.Integer(string='Renk')

    # Bağlantı durumu (connector'dan kopyalanır)
    connection_state = fields.Selection([
        ('draft', 'Bağlanmadı'),
        ('connected', 'Bağlı'),
        ('error', 'Hata'),
        ('warning', 'Uyarı'),
    ], default='draft', string='Durum')
    last_error = fields.Text(string='Son Hata')
    last_sync = fields.Datetime(string='Son Senkronizasyon')

    # İstatistikler (connector'dan hesaplanır)
    order_count = fields.Integer(
        compute='_compute_stats', string='Siparişler')
    pending_order_count = fields.Integer(
        compute='_compute_stats', string='Bekleyen')
    listing_count = fields.Integer(
        compute='_compute_stats', string='Ürünler')

    # Connector referansı
    ref_config_model = fields.Char(string='Config Model', readonly=True)
    ref_config_id = fields.Integer(string='Config ID', readonly=True)

    # ------------------------------------------------------------------
    # İstatistik hesaplama
    # ------------------------------------------------------------------

    @api.depends('channel_type', 'ref_config_model', 'ref_config_id')
    def _compute_stats(self):
        for rec in self:
            rec.order_count = 0
            rec.pending_order_count = 0
            rec.listing_count = 0
            if not rec.ref_config_model or not rec.ref_config_id:
                continue
            Config = self.env.get(rec.ref_config_model)
            if not Config:
                continue
            config = Config.browse(rec.ref_config_id)
            if not config.exists():
                continue
            rec.order_count = config.order_count
            rec.pending_order_count = config.pending_order_count
            rec.listing_count = config.listing_count

    # ------------------------------------------------------------------
    # Açılış aksiyonları
    # ------------------------------------------------------------------

    def action_open_orders(self):
        self.ensure_one()
        models = _CONNECTOR_MODELS.get(self.channel_type)
        if not models or not self.ref_config_id:
            raise UserError(_('Bu kanal için sipariş görünümü bulunamadı.'))
        _, order_model, _ = models
        if not self.env.get(order_model):
            raise UserError(_('%s connector yüklü değil.') % self.channel_type)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Siparişler — %s') % self.name,
            'res_model': order_model,
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.ref_config_id)],
            'context': {'default_config_id': self.ref_config_id},
        }

    def action_open_listings(self):
        self.ensure_one()
        models = _CONNECTOR_MODELS.get(self.channel_type)
        if not models or not self.ref_config_id:
            raise UserError(_('Bu kanal için ürün listesi bulunamadı.'))
        _, _, listing_model = models
        if not self.env.get(listing_model):
            raise UserError(_('%s connector yüklü değil.') % self.channel_type)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ürün Listesi — %s') % self.name,
            'res_model': listing_model,
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.ref_config_id)],
            'context': {'default_config_id': self.ref_config_id},
        }

    def action_open_config(self):
        self.ensure_one()
        models = _CONNECTOR_MODELS.get(self.channel_type)
        if not models or not self.ref_config_id:
            raise UserError(_('Bu kanal için yapılandırma bulunamadı.'))
        config_model, _, _ = models
        if not self.env.get(config_model):
            raise UserError(_('%s connector yüklü değil.') % self.channel_type)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Yapılandırma — %s') % self.name,
            'res_model': config_model,
            'res_id': self.ref_config_id,
            'view_mode': 'form',
        }

    def action_refresh(self):
        """Bağlı connector'dan istatistikleri ve durumu güncelle."""
        for rec in self:
            if not rec.ref_config_model or not rec.ref_config_id:
                continue
            Config = self.env.get(rec.ref_config_model)
            if not Config:
                continue
            config = Config.browse(rec.ref_config_id)
            if not config.exists():
                continue
            vals = {
                'connection_state': config.connection_state,
                'last_error': config.last_error,
            }
            if hasattr(config, 'last_order_sync') and config.last_order_sync:
                vals['last_sync'] = config.last_order_sync
            rec.write(vals)

    # ------------------------------------------------------------------
    # Yardımcı: connector config'den kanal oluştur/güncelle
    # ------------------------------------------------------------------

    @api.model
    def _sync_from_config(self, channel_type, config_record):
        """
        Connector config kaydedildiğinde çağrılır.
        İlgili channel kaydını oluşturur ya da günceller.
        """
        config_model = config_record._name
        channel = self.search([
            ('channel_type', '=', channel_type),
            ('ref_config_model', '=', config_model),
            ('ref_config_id', '=', config_record.id),
        ], limit=1)

        vals = {
            'name': config_record.name,
            'channel_type': channel_type,
            'company_id': config_record.company_id.id,
            'connection_state': config_record.connection_state,
            'last_error': config_record.last_error,
            'ref_config_model': config_model,
            'ref_config_id': config_record.id,
        }
        if hasattr(config_record, 'last_order_sync') and config_record.last_order_sync:
            vals['last_sync'] = config_record.last_order_sync

        if channel:
            channel.write(vals)
        else:
            self.create(vals)
