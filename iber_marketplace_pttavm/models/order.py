from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..core.pttavm_const import ORDER_STATUSES


class IberPttavmOrder(models.Model):
    _name = 'iber.marketplace.pttavm.order'
    _description = 'PttAVM Siparişi'
    _order = 'order_date desc, id desc'
    _rec_name = 'order_number'

    config_id = fields.Many2one(
        'iber.marketplace.pttavm.config', required=True,
        ondelete='cascade', string='Bağlantı')
    company_id = fields.Many2one(
        related='config_id.company_id', store=True, string='Şirket')

    # PttAVM alanları
    pttavm_order_id = fields.Char(
        index=True, readonly=True, string='PttAVM Sipariş ID')
    order_number = fields.Char(
        index=True, readonly=True, string='Sipariş No')
    order_date = fields.Datetime(readonly=True, string='Sipariş Tarihi')
    status = fields.Selection(
        selection=ORDER_STATUSES,
        readonly=True, index=True, string='Durum')
    total_price = fields.Float(readonly=True, string='Toplam Tutar')

    # Müşteri bilgileri
    customer_name = fields.Char(readonly=True, string='Müşteri Adı')
    customer_email = fields.Char(readonly=True, string='E-posta')

    # Teslimat adresi
    ship_address = fields.Char(readonly=True, string='Teslimat Adresi')
    ship_city = fields.Char(readonly=True, string='Teslimat Şehir')
    ship_district = fields.Char(readonly=True, string='Teslimat İlçe')

    # Fatura adresi
    invoice_address = fields.Char(readonly=True, string='Fatura Adresi')
    invoice_city = fields.Char(readonly=True, string='Fatura Şehir')

    # Kargo bilgileri
    cargo_company = fields.Char(readonly=True, string='Kargo Şirketi')
    cargo_tracking_no = fields.Char(string='Kargo Takip No')
    cargo_tracking_url = fields.Char(string='Kargo Takip URL')
    shipment_sent = fields.Boolean(
        default=False, readonly=True, string='Kargo Bilgisi Gönderildi')

    # Odoo bağlantısı
    sale_order_id = fields.Many2one(
        'sale.order', copy=False, string='Satış Siparişi')

    # Satır ilişkisi
    line_ids = fields.One2many(
        'iber.marketplace.pttavm.order.line', 'order_id', string='Kalemler')
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

    def action_send_cargo(self):
        self.ensure_one()
        if not self.cargo_tracking_no:
            raise UserError(_('Kargo takip numarası girilmemiş.'))

        cargo = self.config_id.cargo_company or ''
        if not cargo:
            raise UserError(
                _('Kargo şirketi bilgisi eksik. Lütfen konfigürasyonda '
                  'varsayılan kargo şirketini seçin.'))

        client = self.config_id._get_client()
        try:
            client.send_cargo(
                order_id=self.pttavm_order_id,
                cargo_company=cargo,
                tracking_no=self.cargo_tracking_no,
                tracking_url=self.cargo_tracking_url or '',
            )
        except Exception as exc:
            raise UserError(_('Kargo bilgisi gönderilemedi: %s') % exc)

        self.write({'shipment_sent': True})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _("Kargo bilgisi başarıyla PttAVM'e gönderildi."),
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
                'name': self.customer_name or _('PttAVM Müşterisi'),
                'email': self.customer_email or False,
                'street': self.ship_address or False,
                'city': self.ship_city or False,
                'company_id': self.company_id.id,
            })

        sale_vals = {
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'origin': self.order_number or f'PttAVM #{self.pttavm_order_id}',
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
