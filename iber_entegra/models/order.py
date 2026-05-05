from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..core.entegra_const import CARGO_COMPANIES, ORDER_STATUSES


class IberEntegraOrder(models.Model):
    _name = 'iber.entegra.order'
    _description = 'Entegra Siparişi'
    _order = 'order_date desc, id desc'
    _rec_name = 'order_number'

    config_id = fields.Many2one(
        'iber.entegra.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True)

    # --- Entegra kimlik alanları ---
    entegra_id = fields.Integer(string='Entegra ID', index=True, readonly=True)
    order_number = fields.Char(string='Sipariş No', index=True, readonly=True)
    order_id = fields.Char(string='Pazaryeri Sipariş No', readonly=True)
    supplier = fields.Char(string='Pazaryeri', readonly=True)
    supplier_id = fields.Integer(string='Pazaryeri ID', readonly=True)
    order_date = fields.Datetime(string='Sipariş Tarihi', readonly=True)

    # --- Müşteri ---
    full_name = fields.Char(string='Ad Soyad', readonly=True)
    email = fields.Char(readonly=True)
    mobile_phone = fields.Char(string='GSM', readonly=True)
    phone = fields.Char(string='Telefon', readonly=True)

    # --- Fatura adresi ---
    invoice_fullname = fields.Char(string='Fatura Ad Soyad', readonly=True)
    invoice_address = fields.Char(string='Fatura Adresi', readonly=True)
    invoice_city = fields.Char(string='Fatura Şehir', readonly=True)
    invoice_district = fields.Char(string='Fatura İlçe', readonly=True)
    invoice_postcode = fields.Char(string='Fatura Posta Kodu', readonly=True)
    tax_office = fields.Char(string='Vergi Dairesi', readonly=True)
    tax_number = fields.Char(string='Vergi No', readonly=True)
    tc_id = fields.Char(string='TC No', readonly=True)

    # --- Teslimat adresi ---
    ship_fullname = fields.Char(string='Alıcı Ad Soyad', readonly=True)
    ship_address = fields.Char(string='Teslimat Adresi', readonly=True)
    ship_city = fields.Char(string='Teslimat Şehir', readonly=True)
    ship_district = fields.Char(string='Teslimat İlçe', readonly=True)
    ship_postcode = fields.Char(string='Teslimat Posta Kodu', readonly=True)

    # --- Ödeme & kargo (readonly - Entegra'dan gelir) ---
    payment_type = fields.Char(string='Ödeme Tipi', readonly=True)
    cargo = fields.Char(string='Kargo Şirketi (Entegra)', readonly=True)
    cargo_code = fields.Char(string='Kargo Takip Kodu', readonly=True)
    cargo_payment_method = fields.Char(string='Kargo Ödeme Yöntemi', readonly=True)
    discount = fields.Float(string='İndirim', readonly=True)

    # --- Güncelleme alanları (yazılabilir) ---
    cargo_code2 = fields.Char(string='Kargo Takip Kodu 2')
    cargo_company = fields.Selection(CARGO_COMPANIES, string='Kargo Firması')
    cargo_follow_url = fields.Char(string='Kargo Takip URL')
    cargo_send_date = fields.Date(string='Kargo Gönderim Tarihi')

    status = fields.Selection(ORDER_STATUSES, string='Durum')
    store_order_status = fields.Char(string='Mağaza Sipariş Durumu', readonly=True)

    invoice_url = fields.Char(string='Fatura URL')
    invoice_number = fields.Char(string='Fatura No')
    invoice_date = fields.Datetime(string='Fatura Tarihi')

    # --- ERP senkronizasyon ---
    erp_order_number = fields.Char(string='ERP Sipariş No')
    sync = fields.Integer(string='Sync', default=0, readonly=True)
    api_sync = fields.Integer(string='API Sync', default=0, readonly=True)

    # --- Odoo bağlantısı ---
    sale_order_id = fields.Many2one('sale.order', string='Satış Siparişi', copy=False)

    # --- Kalemler ---
    line_ids = fields.One2many('iber.entegra.order.line', 'order_id', string='Kalemler')

    total_amount = fields.Float(
        string='Toplam', compute='_compute_total_amount', store=True)

    @api.depends('line_ids.price', 'line_ids.quantity')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(l.price * l.quantity for l in rec.line_ids)

    # ------------------------------------------------------------------
    # Aksiyonlar
    # ------------------------------------------------------------------

    def action_update_status(self):
        self.ensure_one()
        if not self.entegra_id:
            raise UserError(_('Entegra ID bulunamadı.'))
        try:
            client = self.config_id._get_client()
            item = {'id': self.entegra_id}
            if self.status:
                item['status'] = self.status
            if self.cargo_code2:
                item['cargo_code2'] = self.cargo_code2
            if self.cargo_company:
                item['cargo_company'] = self.cargo_company
            if self.cargo_follow_url:
                item['cargo_follow_url'] = self.cargo_follow_url
            if self.cargo_send_date:
                item['cargo_send_date'] = str(self.cargo_send_date)
            if self.invoice_url:
                item['invoice_url'] = self.invoice_url
            if self.invoice_number:
                item['invoice_number'] = self.invoice_number
            if self.invoice_date:
                item['invoice_date'] = self.invoice_date.strftime('%Y-%m-%d %H:%M')
            client.update_order({'list': [item]})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Sipariş güncellendi.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as exc:
            raise UserError(_('Sipariş güncellenirken hata: %s') % exc)

    def action_send_shipment(self):
        self.ensure_one()
        if not self.cargo_company:
            raise UserError(_('Kargo firması seçilmeden kargo gönderilemez.'))
        if not self.order_number:
            raise UserError(_('Sipariş numarası bulunamadı.'))
        try:
            client = self.config_id._get_client()
            payload = {'list': {'orders': [
                {'order_number': self.order_number, 'ship_name': self.cargo_company}
            ]}}
            client.send_shipment(payload)
            self.write({'status': '4'})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Kargo servise gönderildi.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as exc:
            raise UserError(_('Kargo gönderilirken hata: %s') % exc)

    def action_mark_erp_synced(self):
        for rec in self:
            if not rec.entegra_id:
                continue
            try:
                client = rec.config_id._get_client()
                payload = {'list': [{
                    'id': rec.entegra_id,
                    'api_sync': 1,
                    'erp_order_number': rec.erp_order_number or '',
                }]}
                client.update_order_erp(payload)
                rec.write({'api_sync': 1})
            except Exception as exc:
                raise UserError(_('ERP sync güncellenirken hata: %s') % exc)

    # ------------------------------------------------------------------
    # Odoo Satış Siparişi Oluşturma
    # ------------------------------------------------------------------

    def action_create_sale_order(self):
        """
        Entegra siparişinden Odoo sale.order oluşturur.
        - Müşteri: email ile ara, yoksa isimle, yoksa yeni oluştur
        - Kalemler: product.mapping üzerinden Odoo ürününe bağla
        - Oluşturulan SO → sale_order_id alanına bağla
        - Entegra'yı api_sync=1 ve erp_order_number ile güncelle
        """
        self.ensure_one()
        if self.sale_order_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.sale_order_id.id,
                'view_mode': 'form',
            }

        # --- Müşteri bul veya oluştur ---
        Partner = self.env['res.partner']
        partner = False
        if self.email:
            partner = Partner.search([('email', '=', self.email)], limit=1)
        if not partner and self.full_name:
            partner = Partner.search([('name', '=', self.full_name)], limit=1)
        if not partner:
            partner_vals = {
                'name': self.full_name or self.invoice_fullname or _('Entegra Müşteri'),
                'email': self.email or False,
                'phone': self.phone or self.mobile_phone or False,
                'street': self.invoice_address or False,
                'city': self.invoice_city or False,
                'zip': self.invoice_postcode or False,
                'vat': self.tax_number or False,
                'customer_rank': 1,
            }
            partner = Partner.create(partner_vals)

        # --- Satış siparişi oluştur ---
        so_vals = {
            'partner_id': partner.id,
            'origin': self.order_number or self.order_id or f'Entegra-{self.entegra_id}',
            'note': f'Pazaryeri: {self.supplier or "-"} | Entegra ID: {self.entegra_id}',
        }
        so = self.env['sale.order'].create(so_vals)

        # --- Kalemler ---
        SoLine = self.env['sale.order.line']
        Mapping = self.env['iber.entegra.product.mapping']
        lines_without_product = []

        for line in self.line_ids:
            # Ürün eşleşmesini bul
            mapping = Mapping.search([
                ('config_id', '=', self.config_id.id),
                ('entegra_product_code', '=', line.product_code),
            ], limit=1)

            if mapping:
                product = mapping.product_id or mapping.product_tmpl_id.product_variant_id
                SoLine.create({
                    'order_id': so.id,
                    'product_id': product.id,
                    'name': line.product_name or product.name,
                    'product_uom_qty': line.quantity,
                    'price_unit': line.price,
                })
            else:
                # Eşleşme yok — notla ekle
                lines_without_product.append(line.product_code or line.product_name)
                SoLine.create({
                    'order_id': so.id,
                    'product_id': self._get_or_create_generic_product().id,
                    'name': f'[{line.product_code}] {line.product_name}',
                    'product_uom_qty': line.quantity,
                    'price_unit': line.price,
                })

        # --- Entegra siparişine bağla ---
        self.write({
            'sale_order_id': so.id,
            'erp_order_number': so.name,
        })

        # --- Entegra'ya api_sync=1 bildir ---
        try:
            client = self.config_id._get_client()
            client.update_order_erp({'list': [{
                'id': self.entegra_id,
                'api_sync': 1,
                'erp_order_number': so.name,
            }]})
            self.write({'api_sync': 1})
        except Exception:
            pass  # Bildirim başarısız olsa da SO oluşturuldu

        msg = _('Satış siparişi oluşturuldu: %s') % so.name
        if lines_without_product:
            msg += _('\nEşleşme bulunamayan ürün kodları: %s') % ', '.join(lines_without_product)

        self.message_post(body=msg)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': so.id,
            'view_mode': 'form',
        }

    def _get_or_create_generic_product(self):
        """Eşleşmesi olmayan kalemler için genel 'Entegra Ürünü' servisi döner."""
        product = self.env['product.product'].search([
            ('default_code', '=', 'ENTEGRA-GENERIC'),
        ], limit=1)
        if not product:
            tmpl = self.env['product.template'].create({
                'name': 'Entegra Ürünü (Eşleşmesiz)',
                'default_code': 'ENTEGRA-GENERIC',
                'type': 'service',
                'sale_ok': True,
                'purchase_ok': False,
            })
            product = tmpl.product_variant_id
        return product
