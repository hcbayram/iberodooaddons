from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..core.trendyol_const import ORDER_STATUSES


class IberTrendyolOrder(models.Model):
    _name = 'iber.marketplace.trendyol.order'
    _description = 'Trendyol Siparişi'
    _order = 'order_date desc, id desc'
    _rec_name = 'order_number'

    config_id = fields.Many2one(
        'iber.marketplace.trendyol.config', required=True,
        ondelete='cascade', string='Bağlantı')
    company_id = fields.Many2one(
        related='config_id.company_id', store=True, string='Şirket')

    # Trendyol alanları
    trendyol_id = fields.Integer(
        index=True, readonly=True, string='Trendyol ID')
    order_number = fields.Char(
        index=True, readonly=True, string='Sipariş No')
    gross_amount = fields.Float(readonly=True, string='Brüt Tutar')
    total_discount = fields.Float(readonly=True, string='Toplam İndirim')
    total_price = fields.Float(readonly=True, string='Toplam Tutar')
    order_date = fields.Datetime(readonly=True, string='Sipariş Tarihi')
    status = fields.Selection(
        selection=ORDER_STATUSES,
        readonly=True, index=True, string='Durum')

    # Müşteri bilgileri
    customer_name = fields.Char(readonly=True, string='Müşteri Adı')
    customer_email = fields.Char(readonly=True, string='E-posta')

    # Adres bilgileri
    invoice_address = fields.Char(readonly=True, string='Fatura Adresi')
    invoice_city = fields.Char(readonly=True, string='Fatura Şehir')
    ship_address = fields.Char(readonly=True, string='Teslimat Adresi')
    ship_city = fields.Char(readonly=True, string='Teslimat Şehir')

    # Kargo bilgileri
    cargo_tracking_number = fields.Char(readonly=True, string='Kargo Takip No')
    cargo_provider = fields.Char(readonly=True, string='Kargo Şirketi (Trendyol)')
    cargo_sender_number = fields.Char(readonly=True, string='Kargo Gönderici No')
    shipment_package_id = fields.Integer(readonly=True, string='Paket ID')
    shipment_sent = fields.Boolean(
        default=False, readonly=True, string='Kargo Bilgisi Gönderildi')

    # Odoo bağlantısı
    sale_order_id = fields.Many2one(
        'sale.order', copy=False, string='Satış Siparişi')

    # Satır ilişkisi
    line_ids = fields.One2many(
        'iber.marketplace.trendyol.order.line', 'order_id', string='Kalemler')
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

    def action_send_shipment(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Bu siparişte kargo gönderilecek kalem bulunamadı.'))
        if not self.cargo_tracking_number:
            raise UserError(_('Kargo takip numarası girilmemiş.'))

        client = self.config_id._get_client()

        lines = []
        for line in self.line_ids:
            cargo_provider = (
                line.cargo_provider_name
                or self.config_id.cargo_provider_name
                or self.cargo_provider
                or ''
            )
            if not cargo_provider:
                raise UserError(
                    _('Kargo şirketi bilgisi eksik. Lütfen konfigürasyonda '
                      'varsayılan kargo şirketini seçin.'))

            line_dict = {
                'orderLineId': line.trendyol_line_id,
                'cargoProviderName': cargo_provider,
                'trackingNumber': self.cargo_tracking_number,
            }
            if self.shipment_package_id:
                line_dict['shipmentPackageId'] = self.shipment_package_id
            lines.append(line_dict)

        try:
            client.update_shipment(lines)
        except Exception as exc:
            raise UserError(_('Kargo bilgisi gönderilemedi: %s') % exc)

        self.write({
            'shipment_sent': True,
            'cargo_provider': (
                self.config_id.cargo_provider_name or self.cargo_provider or ''
            ),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Kargo bilgisi başarıyla Trendyol\'a gönderildi.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_create_sale_order(self):
        self.ensure_one()
        if self.sale_order_id:
            raise UserError(_('Bu siparişe zaten bir satış siparişi bağlı.'))

        partner = self.env['res.partner'].search(
            [('name', '=', self.customer_name)], limit=1
        )
        if not partner:
            partner = self.env['res.partner'].create({
                'name': self.customer_name or _('Trendyol Müşterisi'),
                'email': self.customer_email or False,
                'street': self.ship_address or False,
                'city': self.ship_city or False,
                'company_id': self.company_id.id,
            })

        sale_vals = {
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'origin': self.order_number or f'Trendyol #{self.trendyol_id}',
            'order_line': [],
        }
        for line in self.line_ids:
            product = line.product_id
            if not product:
                product = self.env['product.product'].search(
                    [('barcode', '=', line.barcode)], limit=1
                )
            if not product:
                continue
            sale_vals['order_line'].append((0, 0, {
                'product_id': product.id,
                'product_uom_qty': line.quantity,
                'price_unit': line.price,
                'name': line.product_name or product.name,
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
