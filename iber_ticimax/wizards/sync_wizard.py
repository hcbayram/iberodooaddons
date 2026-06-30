from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberTicimaxSyncWizard(models.TransientModel):
    _name = 'iber.ticimax.sync.wizard'
    _description = 'Ticimax Senkronizasyon Sihirbazı'

    config_id = fields.Many2one(
        'iber.ticimax.config', required=True, string='Bağlantı')
    sync_type = fields.Selection([
        ('categories', 'Kategoriler'),
        ('brands', 'Markalar'),
        ('orders', 'Siparişler'),
        ('all_orders', 'Tüm Siparişler (Aktarılmamış)'),
        ('products', 'Ürünleri Dışa Aktar'),
    ], default='orders', required=True, string='Senkronizasyon Türü')

    # Sipariş filtresi
    siparis_durum_filtre = fields.Selection([
        ('-1', 'Tümü'),
        ('1', 'Onay Bekliyor'),
        ('2', 'Onaylandı'),
        ('3', 'Ödeme Bekliyor'),
        ('4', 'Paketleniyor'),
        ('5', 'Tedarik Ediliyor'),
        ('6', 'Kargoya Verildi'),
    ], default='-1', string='Sipariş Durumu Filtresi')
    entegrasyon_aktarilmamis = fields.Boolean(
        string='Sadece ERP\'ye Aktarılmamış', default=True)

    result_message = fields.Text(string='Sonuç', readonly=True)
    state = fields.Selection([
        ('draft', 'Hazır'),
        ('done', 'Tamamlandı'),
    ], default='draft')

    def action_sync(self):
        self.ensure_one()
        config = self.config_id
        try:
            if self.sync_type == 'categories':
                count = self.env['iber.ticimax.category'].sync_from_ticimax(config.id)
                msg = _('%d kategori senkronize edildi.') % count

            elif self.sync_type == 'brands':
                count = self.env['iber.ticimax.brand'].sync_from_ticimax(config.id)
                msg = _('%d marka senkronize edildi.') % count

            elif self.sync_type in ('orders', 'all_orders'):
                filtre = {}
                if self.entegrasyon_aktarilmamis:
                    filtre['EntegrasyonAktarildi'] = 0
                if self.siparis_durum_filtre and self.siparis_durum_filtre != '-1':
                    filtre['SiparisDurumu'] = int(self.siparis_durum_filtre)
                count = self.env['iber.ticimax.order'].sync_from_ticimax(
                    config.id, filtre=filtre)
                msg = _('%d sipariş içe aktarıldı.') % count

            elif self.sync_type == 'products':
                products = self.env['iber.ticimax.product'].search([
                    ('config_id', '=', config.id),
                    ('sync_state', 'in', ('pending', 'error')),
                ])
                count = 0
                errors = 0
                for p in products:
                    try:
                        p.action_push_to_ticimax()
                        count += 1
                    except Exception:
                        errors += 1
                msg = _('%d ürün gönderildi, %d hata.') % (count, errors)
            else:
                msg = _('Geçersiz senkronizasyon türü.')

            self.write({'result_message': msg, 'state': 'done'})
        except Exception as exc:
            raise UserError(_('Senkronizasyon hatası: %s') % exc)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}
