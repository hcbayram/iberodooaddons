from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberTicimaxCategory(models.Model):
    _name = 'iber.ticimax.category'
    _description = 'Ticimax Kategori'
    _rec_name = 'tanim'
    _order = 'tanim'

    config_id = fields.Many2one(
        'iber.ticimax.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True)

    ticimax_id = fields.Integer(string='Ticimax ID', index=True, readonly=True)
    pid = fields.Integer(string='Üst Kategori ID', readonly=True)
    tanim = fields.Char(string='Kategori Adı', readonly=True)
    kod = fields.Char(string='Kategori Kodu', readonly=True)
    aktif = fields.Boolean(string='Aktif', readonly=True)
    seo_anahtar_kelime = fields.Char(string='SEO Anahtar Kelime', readonly=True)
    seo_sayfa_aciklama = fields.Char(string='SEO Açıklama', readonly=True)
    seo_sayfa_baslik = fields.Char(string='SEO Başlık', readonly=True)

    parent_id = fields.Many2one(
        'iber.ticimax.category',
        string='Üst Kategori',
        compute='_compute_parent_id',
        store=True,
    )
    odoo_category_id = fields.Many2one(
        'product.category',
        string='Odoo Kategorisi',
    )

    @api.depends('pid', 'config_id')
    def _compute_parent_id(self):
        for rec in self:
            if rec.pid and rec.pid != 0:
                parent = self.search([
                    ('config_id', '=', rec.config_id.id),
                    ('ticimax_id', '=', rec.pid),
                ], limit=1)
                rec.parent_id = parent
            else:
                rec.parent_id = False

    def action_push_to_ticimax(self):
        self.ensure_one()
        try:
            client = self.config_id._get_client()
            result = client.save_kategori(
                id=self.ticimax_id or 0,
                pid=self.pid or 0,
                aktif=self.aktif,
                tanim=self.tanim or '',
                kod=self.kod or '',
                seo_anahtar_kelime=self.seo_anahtar_kelime or '',
                seo_sayfa_aciklama=self.seo_sayfa_aciklama or '',
                seo_sayfa_baslik=self.seo_sayfa_baslik or '',
            )
            if result and not self.ticimax_id:
                self.ticimax_id = int(result)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Kategori Ticimax\'a gönderildi.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as exc:
            raise UserError(_('Kategori gönderilemedi: %s') % exc)

    @api.model
    def sync_from_ticimax(self, config_id):
        config = self.env['iber.ticimax.config'].browse(config_id)
        client = config._get_client()
        kategoriler = client.select_kategori(0)
        synced = 0
        for k in kategoriler:
            vals = {
                'config_id': config.id,
                'ticimax_id': int(k.get('ID', 0)),
                'pid': int(k.get('PID', 0)),
                'tanim': k.get('Tanim', ''),
                'kod': k.get('Kod', ''),
                'aktif': str(k.get('Aktif', 'true')).lower() == 'true',
                'seo_anahtar_kelime': k.get('SeoAnahtarKelime', ''),
                'seo_sayfa_aciklama': k.get('SeoSayfaAciklama', ''),
                'seo_sayfa_baslik': k.get('SeoSayfaBaslik', ''),
            }
            existing = self.search([
                ('config_id', '=', config.id),
                ('ticimax_id', '=', vals['ticimax_id']),
            ], limit=1)
            if existing:
                existing.write(vals)
            else:
                self.create(vals)
            synced += 1
        config.write({'last_category_sync': fields.Datetime.now()})
        return synced
