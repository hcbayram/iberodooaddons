from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberTicimaxProduct(models.Model):
    _name = 'iber.ticimax.product'
    _description = 'Ticimax Ürün Eşleşmesi'
    _rec_name = 'display_name'
    _order = 'write_date desc'

    config_id = fields.Many2one(
        'iber.ticimax.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True)

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Odoo Ürünü',
        required=True,
        ondelete='cascade',
    )
    ticimax_id = fields.Integer(
        string='Ticimax Kart ID', index=True, readonly=True)
    ticimax_kategori_id = fields.Many2one(
        'iber.ticimax.category', string='Ticimax Kategorisi')
    ticimax_marka_id = fields.Many2one(
        'iber.ticimax.brand', string='Ticimax Markası')

    sync_state = fields.Selection([
        ('pending', 'Bekliyor'),
        ('synced', 'Senkronize'),
        ('error', 'Hata'),
    ], default='pending', readonly=True)
    last_sync = fields.Datetime(string='Son Sync', readonly=True)
    last_error = fields.Text(string='Son Hata', readonly=True)

    display_name = fields.Char(
        compute='_compute_display_name', store=True)

    @api.depends('product_tmpl_id', 'ticimax_id')
    def _compute_display_name(self):
        for rec in self:
            name = rec.product_tmpl_id.name or ''
            if rec.ticimax_id:
                name = f'[{rec.ticimax_id}] {name}'
            rec.display_name = name

    def action_push_to_ticimax(self):
        self.ensure_one()
        tmpl = self.product_tmpl_id
        try:
            client = self.config_id._get_client()

            kategori_id = (
                self.ticimax_kategori_id.ticimax_id
                if self.ticimax_kategori_id else 0
            )
            marka_id = (
                self.ticimax_marka_id.ticimax_id
                if self.ticimax_marka_id else 0
            )

            varyasyonlar = []
            for variant in tmpl.product_variant_ids:
                ozellikler = []
                for val in variant.product_template_attribute_value_ids:
                    ozellikler.append({
                        'Tanim': val.attribute_id.name,
                        'Deger': val.name,
                    })
                varyasyonlar.append({
                    'ID': 0,
                    'Aktif': variant.active,
                    'AlisFiyati': float(variant.standard_price),
                    'Barkod': variant.barcode or '',
                    'Desi': 0,
                    'KargoUcreti': 0,
                    'KdvDahil': False,
                    'KdvOrani': 18,
                    'Ozellikler': ozellikler,
                    'ParaBirimiID': 1,
                    'Resimler': [],
                    'SatisFiyati': float(variant.lst_price),
                    'StokAdedi': int(variant.qty_available),
                    'StokKodu': variant.default_code or '',
                })

            urun_karti = {
                'ID': self.ticimax_id or 0,
                'Aktif': tmpl.active,
                'UrunAdi': tmpl.name,
                'Aciklama': tmpl.description_sale or '',
                'AnaKategoriID': kategori_id,
                'AnaKategori': self.ticimax_kategori_id.tanim or '',
                'Kategoriler': [kategori_id] if kategori_id else [],
                'MarkaID': marka_id,
                'Resimler': [],
                'SatisBirimi': tmpl.uom_id.name if tmpl.uom_id else 'Adet',
                'UcretsizKargo': False,
                'Varyasyonlar': varyasyonlar,
                'Vitrin': False,
                'YeniUrun': False,
            }

            result = client.save_urun(
                urun_kartlari=[urun_karti],
                urun_karti_ayar={
                    'AciklamaGuncelle': True,
                    'AktifGuncelle': True,
                    'UrunAdiGuncelle': True,
                    'KategoriGuncelle': True,
                    'MarkaGuncelle': True,
                },
                varyasyon_ayar={
                    'SatisFiyatiGuncelle': True,
                    'StokAdediGuncelle': True,
                    'AlisFiyatiGuncelle': True,
                    'BarkodGuncelle': True,
                },
            )
            new_id = self.ticimax_id
            if result and isinstance(result, list) and result[0]:
                try:
                    new_id = int(result[0].get('ID', self.ticimax_id or 0))
                except (TypeError, ValueError):
                    pass
            self.write({
                'ticimax_id': new_id,
                'sync_state': 'synced',
                'last_sync': fields.Datetime.now(),
                'last_error': False,
            })
            # CustomServis entegrasyon ID kaydı
            if new_id:
                try:
                    client.save_entegrasyon_id(
                        entegrasyon_kodu='ODOO',
                        tablo_alan='TICIMAXURUNID',
                        alan_deger=str(new_id),
                        tanim='ODOOURUNID',
                        deger=str(tmpl.id),
                    )
                except Exception:
                    pass
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Ürün Ticimax\'a gönderildi.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as exc:
            self.write({'sync_state': 'error', 'last_error': str(exc)})
            raise UserError(_('Ürün gönderilemedi: %s') % exc)
