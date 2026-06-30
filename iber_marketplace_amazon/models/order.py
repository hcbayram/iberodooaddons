from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..core.amazon_const import ORDER_STATUSES, CARRIER_CODES


class IberAmazonOrder(models.Model):
    _name = 'iber.marketplace.amazon.order'
    _description = 'Amazon TR Siparişi'
    _order = 'purchase_date desc, id desc'
    _rec_name = 'amazon_order_id'

    config_id = fields.Many2one(
        'iber.marketplace.amazon.config', required=True,
        ondelete='cascade', string='Bağlantı')
    company_id = fields.Many2one(
        related='config_id.company_id', store=True, string='Şirket')

    # Amazon alanları
    amazon_order_id = fields.Char(
        index=True, readonly=True, string='Amazon Sipariş No')
    purchase_date = fields.Datetime(readonly=True, string='Sipariş Tarihi')
    status = fields.Selection(
        selection=ORDER_STATUSES, readonly=True, index=True, string='Durum')
    fulfillment_channel = fields.Selection([
        ('AFN', 'FBA (Amazon Fulfillment)'),
        ('MFN', 'MFN (Satıcı Kargosu)'),
    ], readonly=True, string='Gönderim Kanalı')

    # Müşteri bilgileri
    buyer_name = fields.Char(readonly=True, string='Alıcı Adı')
    buyer_email = fields.Char(readonly=True, string='Alıcı E-posta')

    # Teslimat adresi
    ship_name = fields.Char(readonly=True, string='Teslimat Adı')
    ship_address_line1 = fields.Char(readonly=True, string='Adres 1')
    ship_address_line2 = fields.Char(readonly=True, string='Adres 2')
    ship_city = fields.Char(readonly=True, string='Şehir')
    ship_state = fields.Char(readonly=True, string='İl')
    ship_postal_code = fields.Char(readonly=True, string='Posta Kodu')
    ship_country_code = fields.Char(readonly=True, string='Ülke Kodu')

    # Tutar
    order_total = fields.Float(readonly=True, string='Toplam Tutar')
    currency_code = fields.Char(readonly=True, string='Para Birimi', default='TRY')

    # Kargo (MFN siparişler için)
    carrier_code = fields.Selection(
        selection=CARRIER_CODES, string='Kargo Şirketi')
    tracking_number = fields.Char(string='Kargo Takip No')
    shipment_sent = fields.Boolean(
        default=False, readonly=True, string='Kargo Onaylandı')

    # Odoo bağlantısı
    sale_order_id = fields.Many2one(
        'sale.order', copy=False, string='Satış Siparişi')

    # Satır ilişkisi
    line_ids = fields.One2many(
        'iber.marketplace.amazon.order.line', 'order_id', string='Kalemler')
    total_lines = fields.Integer(compute='_compute_total_lines', string='Kalem Sayısı')

    # ------------------------------------------------------------------
    # Hesaplanan alanlar
    # ------------------------------------------------------------------

    @api.depends('line_ids')
    def _compute_total_lines(self):
        for rec in self:
            rec.total_lines = len(rec.line_ids)

    # ------------------------------------------------------------------
    # Aksiyonlar
    # ------------------------------------------------------------------

    def action_confirm_shipment(self):
        self.ensure_one()
        if self.fulfillment_channel == 'AFN':
            raise UserError(_('FBA siparişleri için kargo onayı gerekli değildir.'))
        if not self.tracking_number:
            raise UserError(_('Kargo takip numarası girilmemiş.'))
        carrier = self.carrier_code or self.config_id.default_carrier_code
        if not carrier:
            raise UserError(
                _('Kargo şirketi seçilmemiş. Lütfen siparişte veya '
                  'konfigürasyonda kargo şirketini belirtin.'))

        items = [
            {
                'orderItemId': line.order_item_id,
                'quantity': int(line.quantity_ordered),
            }
            for line in self.line_ids
        ]

        client = self.config_id._get_client()
        try:
            client.confirm_shipment(
                amazon_order_id=self.amazon_order_id,
                carrier_code=carrier,
                tracking_number=self.tracking_number,
                items=items,
            )
        except Exception as exc:
            raise UserError(_('Kargo onayı gönderilemedi: %s') % exc)

        self.write({'shipment_sent': True})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Kargo onayı Amazon\'a başarıyla gönderildi.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_create_sale_order(self):
        self.ensure_one()
        if self.sale_order_id:
            raise UserError(_('Bu siparişe zaten bir satış siparişi bağlı.'))

        partner = self.env['res.partner'].search(
            [('name', '=', self.buyer_name or self.ship_name)], limit=1
        )
        if not partner:
            partner = self.env['res.partner'].create({
                'name': self.buyer_name or self.ship_name or _('Amazon Müşterisi'),
                'email': self.buyer_email or False,
                'street': self.ship_address_line1 or False,
                'street2': self.ship_address_line2 or False,
                'city': self.ship_city or False,
                'zip': self.ship_postal_code or False,
                'company_id': self.company_id.id,
            })

        sale_vals = {
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'origin': self.amazon_order_id or f'Amazon #{self.id}',
            'order_line': [],
        }
        for line in self.line_ids:
            product = line.product_id
            if not product:
                product = self.env['product.product'].search(
                    [('default_code', '=', line.seller_sku)], limit=1
                )
            if not product:
                continue
            sale_vals['order_line'].append((0, 0, {
                'product_id': product.id,
                'product_uom_qty': line.quantity_ordered,
                'price_unit': line.item_price,
                'name': line.title or product.name,
            }))

        sale_order = self.env['sale.order'].create(sale_vals)
        self.write({'sale_order_id': sale_order.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Satış Siparişi'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
        }
