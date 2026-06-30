from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberTicimaxBrand(models.Model):
    _name = 'iber.ticimax.brand'
    _description = 'Ticimax Marka'
    _rec_name = 'tanim'
    _order = 'tanim'

    config_id = fields.Many2one(
        'iber.ticimax.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True)

    ticimax_id = fields.Integer(string='Ticimax ID', index=True, readonly=True)
    tanim = fields.Char(string='Marka Adı', readonly=True)
    aktif = fields.Boolean(string='Aktif', readonly=True)
    seo_anahtar_kelime = fields.Char(string='SEO Anahtar Kelime', readonly=True)
    seo_sayfa_aciklama = fields.Char(string='SEO Açıklama', readonly=True)
    seo_sayfa_baslik = fields.Char(string='SEO Başlık', readonly=True)

    @api.model
    def sync_from_ticimax(self, config_id):
        config = self.env['iber.ticimax.config'].browse(config_id)
        client = config._get_client()
        markalar = client.select_marka(0)
        synced = 0
        for m in markalar:
            vals = {
                'config_id': config.id,
                'ticimax_id': int(m.get('ID', 0)),
                'tanim': m.get('Tanim', ''),
                'aktif': str(m.get('Aktif', 'true')).lower() == 'true',
                'seo_anahtar_kelime': m.get('SeoAnahtarKelime', ''),
                'seo_sayfa_aciklama': m.get('SeoSayfaAciklama', ''),
                'seo_sayfa_baslik': m.get('SeoSayfaBaslik', ''),
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
        config.write({'last_brand_sync': fields.Datetime.now()})
        return synced

    def action_push_to_ticimax(self):
        self.ensure_one()
        try:
            client = self.config_id._get_client()
            client.save_marka(
                id=self.ticimax_id or 0,
                aktif=self.aktif,
                tanim=self.tanim or '',
                seo_anahtar_kelime=self.seo_anahtar_kelime or '',
                seo_sayfa_aciklama=self.seo_sayfa_aciklama or '',
                seo_sayfa_baslik=self.seo_sayfa_baslik or '',
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Marka Ticimax\'a gönderildi.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as exc:
            raise UserError(_('Marka gönderilemedi: %s') % exc)
