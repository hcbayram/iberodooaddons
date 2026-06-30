from odoo import models, fields, api, _
from odoo.exceptions import UserError

SIPARIS_DURUMU = [
    ('0', 'Ön Sipariş'),
    ('1', 'Onay Bekliyor'),
    ('2', 'Onaylandı'),
    ('3', 'Ödeme Bekliyor'),
    ('4', 'Paketleniyor'),
    ('5', 'Tedarik Ediliyor'),
    ('6', 'Kargoya Verildi'),
    ('7', 'Teslim Edildi'),
    ('8', 'İptal Edildi'),
    ('9', 'İade Edildi'),
]

ODEME_TIPI = [
    ('0', 'Kredi Kartı'),
    ('1', 'Havale'),
    ('2', 'Kapıda Ödeme Nakit'),
    ('3', 'Kapıda Ödeme Kredi Kartı'),
    ('4', 'Mobil Ödeme'),
    ('6', 'PayPal'),
    ('7', 'Cari'),
    ('8', 'Mail Order'),
    ('9', 'iPara'),
    ('10', 'Nakit'),
]

ODEME_DURUMU = [
    ('0', 'Onay Bekliyor'),
    ('1', 'Onaylandı'),
    ('2', 'Hatalı'),
    ('3', 'İade Edilmiş'),
    ('4', 'İptal Edilmiş'),
]


class IberTicimaxOrder(models.Model):
    _name = 'iber.ticimax.order'
    _description = 'Ticimax Siparişi'
    _order = 'siparis_tarihi desc, id desc'
    _rec_name = 'ticimax_id'

    config_id = fields.Many2one(
        'iber.ticimax.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True)

    ticimax_id = fields.Integer(string='Ticimax Sipariş ID', index=True, readonly=True)
    siparis_durumu = fields.Selection(SIPARIS_DURUMU, string='Sipariş Durumu', readonly=True)
    odeme_tipi = fields.Selection(ODEME_TIPI, string='Ödeme Tipi', readonly=True)
    odeme_durumu = fields.Selection(ODEME_DURUMU, string='Ödeme Durumu', readonly=True)
    siparis_tarihi = fields.Datetime(string='Sipariş Tarihi', readonly=True)
    siparis_kaynagi = fields.Char(string='Sipariş Kaynağı', readonly=True)

    # Müşteri
    uye_id = fields.Integer(string='Ticimax Üye ID', readonly=True)
    uye_adi = fields.Char(string='Üye Adı', readonly=True)
    uye_mail = fields.Char(string='Üye E-posta', readonly=True)
    uye_telefon = fields.Char(string='Üye Telefon', readonly=True)

    # Fatura adresi
    fatura_adresi = fields.Text(string='Fatura Adresi', readonly=True)
    fatura_sehir = fields.Char(string='Fatura Şehir', readonly=True)
    fatura_ilce = fields.Char(string='Fatura İlçe', readonly=True)

    # Teslimat adresi
    teslimat_adresi = fields.Text(string='Teslimat Adresi', readonly=True)
    teslimat_sehir = fields.Char(string='Teslimat Şehir', readonly=True)
    teslimat_ilce = fields.Char(string='Teslimat İlçe', readonly=True)

    # Kargo
    kargo_firma = fields.Char(string='Kargo Firması', readonly=True)
    kargo_takip_no = fields.Char(string='Kargo Takip No', readonly=True)

    # Tutar
    toplam_tutar = fields.Float(
        string='Toplam', compute='_compute_toplam', store=True)
    indirim = fields.Float(string='İndirim', readonly=True)

    entegrasyon_aktarildi = fields.Boolean(
        string='ERP\'ye Aktarıldı', default=False, readonly=True)

    line_ids = fields.One2many(
        'iber.ticimax.order.line', 'order_id', string='Kalemler')
    sale_order_id = fields.Many2one(
        'sale.order', string='Satış Siparişi', copy=False)

    @api.depends('line_ids.tutar', 'line_ids.adet')
    def _compute_toplam(self):
        for rec in self:
            rec.toplam_tutar = sum(l.tutar * l.adet for l in rec.line_ids)

    # ------------------------------------------------------------------
    # Odoo Satış Siparişi Oluşturma
    # ------------------------------------------------------------------

    def action_create_sale_order(self):
        self.ensure_one()
        if self.sale_order_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.sale_order_id.id,
                'view_mode': 'form',
            }

        Partner = self.env['res.partner']
        partner = False
        if self.uye_mail:
            partner = Partner.search([('email', '=', self.uye_mail)], limit=1)
        if not partner and self.uye_adi:
            partner = Partner.search([('name', '=', self.uye_adi)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': self.uye_adi or _('Ticimax Müşteri'),
                'email': self.uye_mail or False,
                'phone': self.uye_telefon or False,
                'street': self.fatura_adresi or False,
                'city': self.fatura_sehir or False,
                'customer_rank': 1,
            })

        so = self.env['sale.order'].create({
            'partner_id': partner.id,
            'origin': f'Ticimax-{self.ticimax_id}',
            'note': f'Ticimax Sipariş ID: {self.ticimax_id} | {self.siparis_kaynagi or ""}',
        })

        Product = self.env['product.product']
        for line in self.line_ids:
            product = False
            if line.stok_kodu:
                product = Product.search([
                    ('default_code', '=', line.stok_kodu)
                ], limit=1)
            if not product:
                product = self._get_or_create_generic_product()
            self.env['sale.order.line'].create({
                'order_id': so.id,
                'product_id': product.id,
                'name': f'[{line.stok_kodu or "?"}] {line.urun_adi}' if line.stok_kodu else line.urun_adi,
                'product_uom_qty': line.adet,
                'price_unit': line.tutar,
            })

        self.write({
            'sale_order_id': so.id,
            'entegrasyon_aktarildi': True,
        })
        self.message_post(body=_('Satış siparişi oluşturuldu: %s') % so.name)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': so.id,
            'view_mode': 'form',
        }

    def _get_or_create_generic_product(self):
        product = self.env['product.product'].search([
            ('default_code', '=', 'TICIMAX-GENERIC'),
        ], limit=1)
        if not product:
            tmpl = self.env['product.template'].create({
                'name': 'Ticimax Ürünü (Eşleşmesiz)',
                'default_code': 'TICIMAX-GENERIC',
                'type': 'service',
                'sale_ok': True,
            })
            product = tmpl.product_variant_id
        return product

    @api.model
    def sync_from_ticimax(self, config_id, filtre=None):
        config = self.env['iber.ticimax.config'].browse(config_id)
        client = config._get_client()
        filtre = filtre or {'EntegrasyonAktarildi': 0}
        sayfalama = {'BaslangicIndex': 0, 'KayitSayisi': 100, 'SiralamaYonu': 'DESC'}
        siparisler = client.select_siparis(filtre=filtre, sayfalama=sayfalama)
        synced = 0
        for s in siparisler:
            ticimax_id = int(s.get('ID', 0))
            if not ticimax_id:
                continue
            existing = self.search([
                ('config_id', '=', config.id),
                ('ticimax_id', '=', ticimax_id),
            ], limit=1)
            vals = {
                'config_id': config.id,
                'ticimax_id': ticimax_id,
                'siparis_durumu': str(s.get('SiparisDurumu', '')),
                'odeme_tipi': str(s.get('OdemeTipi', '')),
                'odeme_durumu': str(s.get('OdemeDurumu', '')),
                'siparis_kaynagi': s.get('SiparisKaynagi', ''),
                'uye_id': int(s.get('UyeID', 0)),
                'uye_adi': s.get('UyeAdi', ''),
                'uye_mail': s.get('UyeMail', ''),
                'uye_telefon': s.get('UyeTelefon', ''),
                'fatura_adresi': s.get('FaturaAdresi', ''),
                'fatura_sehir': s.get('FaturaSehir', ''),
                'fatura_ilce': s.get('FaturaIlce', ''),
                'teslimat_adresi': s.get('TeslimatAdresi', ''),
                'teslimat_sehir': s.get('TeslimatSehir', ''),
                'teslimat_ilce': s.get('TeslimatIlce', ''),
                'kargo_firma': s.get('KargoFirma', ''),
                'kargo_takip_no': s.get('KargoTakipNo', ''),
                'indirim': float(s.get('Indirim', 0) or 0),
                'entegrasyon_aktarildi': str(s.get('EntegrasyonAktarildi', '0')) != '0',
            }
            siparis_tarihi = s.get('SiparisTarihi', '')
            if siparis_tarihi:
                try:
                    from datetime import datetime
                    vals['siparis_tarihi'] = datetime.fromisoformat(
                        siparis_tarihi.replace('T', ' ')[:19])
                except Exception:
                    pass

            if existing:
                existing.write(vals)
                order_rec = existing
            else:
                order_rec = self.create(vals)

            # Kalemler
            urun_listesi = client.select_siparis_urun(ticimax_id)
            order_rec.line_ids.unlink()
            for u in urun_listesi:
                self.env['iber.ticimax.order.line'].create({
                    'order_id': order_rec.id,
                    'ticimax_urun_id': int(u.get('UrunID', 0)),
                    'urun_adi': u.get('UrunAdi', ''),
                    'stok_kodu': u.get('StokKodu', ''),
                    'barkod': u.get('Barkod', ''),
                    'adet': float(u.get('Adet', 1) or 1),
                    'tutar': float(u.get('Tutar', 0) or 0),
                    'kdv_orani': float(u.get('KdvOrani', 0) or 0),
                    'kdv_tutari': float(u.get('KdvTutari', 0) or 0),
                })
            synced += 1
        config.write({'last_order_sync': fields.Datetime.now()})
        return synced
