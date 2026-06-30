import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberPavoTransaction(models.Model):
    _name = 'iber.pavo.transaction'
    _description = 'Pavo Ödeme İşlemi'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(compute='_compute_name', store=True)
    terminal_id = fields.Many2one(
        'iber.pavo.terminal', required=True, ondelete='restrict', string='Terminal')
    company_id = fields.Many2one(
        'res.company', related='terminal_id.company_id', store=True)

    sale_type = fields.Selection([
        ('sale', 'Sepet Satış'),
        ('advance', 'Avans Ödeme'),
        ('current', 'Cari Ödeme'),
    ], string='İşlem Tipi', required=True)

    order_no = fields.Char(string='Sipariş No')
    sale_number = fields.Char(string='Satış No', readonly=True)
    pavo_sale_id = fields.Integer(string='Pavo Satış ID', readonly=True)
    sale_reason = fields.Char(string='Satış Nedeni')

    amount = fields.Float(string='Tutar', digits=(16, 2))
    currency_code = fields.Char(string='Para Birimi', default='TRY')

    state = fields.Selection([
        ('pending', 'Bekliyor'),
        ('success', 'Başarılı'),
        ('failed', 'Başarısız'),
        ('cancelled', 'İptal'),
    ], default='pending', readonly=True)

    invoice_id = fields.Many2one(
        'account.move', string='Fatura', ondelete='set null')

    request_json = fields.Text(string='İstek (JSON)', readonly=True)
    response_json = fields.Text(string='Yanıt (JSON)', readonly=True)
    last_error = fields.Text(string='Son Hata', readonly=True)

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    @api.depends('sale_type', 'order_no', 'sale_number', 'create_date')
    def _compute_name(self):
        type_labels = {'sale': 'Satış', 'advance': 'Avans', 'current': 'Cari'}
        for rec in self:
            label = type_labels.get(rec.sale_type, 'İşlem')
            ref = rec.sale_number or rec.order_no or (
                rec.create_date.strftime('%Y%m%d%H%M') if rec.create_date else '')
            rec.name = f'{label} / {ref}' if ref else label

    # ------------------------------------------------------------------
    # Sorgu aksiyonu
    # ------------------------------------------------------------------

    def action_query_result(self):
        self.ensure_one()
        if not self.sale_number and not self.order_no and not self.pavo_sale_id:
            raise UserError(_(
                'Satış No, Sipariş No veya Pavo Satış ID bilgisi olmadan sorgu yapılamaz.'))
        try:
            client = self.terminal_id._get_client()
            result = client.get_sale_result(
                sale_number=self.sale_number or None,
                order_no=self.order_no or None,
                sale_id=self.pavo_sale_id or None,
            )
            self._apply_result(result)
            return self.terminal_id._notify(
                _('Satış durumu güncellendi: %s') % self.state, 'success')
        except Exception as exc:
            self.write({'last_error': str(exc)})
            raise UserError(_('Sorgu hatası: %s') % exc)

    def _apply_result(self, result):
        """Pavo yanıtından state ve sale_number güncelle."""
        sale = result.get('Sale') or result.get('Data') or {}
        vals = {'response_json': json.dumps(result, ensure_ascii=False, indent=2)}

        pavo_state = sale.get('SaleStatus') or sale.get('Status') or ''
        if pavo_state in ('Completed', 'Successful', '1'):
            vals['state'] = 'success'
        elif pavo_state in ('Cancelled', 'Canceled', '4'):
            vals['state'] = 'cancelled'
        elif pavo_state in ('Failed', '3'):
            vals['state'] = 'failed'

        if sale.get('SaleNumber'):
            vals['sale_number'] = sale['SaleNumber']
        if sale.get('Id'):
            vals['pavo_sale_id'] = sale['Id']

        self.write(vals)
