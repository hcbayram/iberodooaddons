import json
import uuid
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberPavoPaymentWizard(models.TransientModel):
    _name = 'iber.pavo.payment.wizard'
    _description = 'Pavo POS Ödeme Sihirbazı'

    invoice_id = fields.Many2one('account.move', string='Fatura', readonly=True)
    terminal_id = fields.Many2one('iber.pavo.terminal', string='Terminal', required=True,
                                  domain=[('state', '=', 'paired')])

    sale_type = fields.Selection([
        ('sale', 'Sepet Satış'),
        ('advance', 'Avans Ödeme'),
        ('current', 'Cari Ödeme'),
    ], string='İşlem Tipi', required=True, default='sale')

    amount = fields.Float(string='Tutar', digits=(16, 2))
    sale_reason = fields.Char(string='Satış Nedeni', default='Odoo Fatura Ödemesi')

    order_no = fields.Char(string='Sipariş No',
                           help='Boş bırakılırsa otomatik oluşturulur.')
    currency_code = fields.Char(string='Para Birimi', default='TRY')
    main_document_type = fields.Selection([
        ('1', 'İade Bilgi Fişi'),
        ('0', 'e-Fatura'),
    ], string='Belge Tipi', default='1')

    # Sonuç bilgileri
    result_state = fields.Selection([
        ('pending', 'Bekliyor'),
        ('success', 'Başarılı'),
        ('failed', 'Başarısız'),
    ], readonly=True)
    result_message = fields.Text(string='Sonuç', readonly=True)
    transaction_id = fields.Many2one('iber.pavo.transaction', readonly=True)

    # ------------------------------------------------------------------
    # Defaults / onchange
    # ------------------------------------------------------------------

    @api.onchange('invoice_id')
    def _onchange_invoice(self):
        if self.invoice_id:
            self.amount = self.invoice_id.amount_residual
            if self.invoice_id.move_type == 'in_invoice':
                self.sale_type = 'current'

    @api.onchange('sale_type')
    def _onchange_sale_type(self):
        if self.sale_type == 'current' and not self.sale_reason:
            self.sale_reason = 'Cari İşlem Tahsilatı'
        elif self.sale_type == 'advance' and not self.sale_reason:
            self.sale_reason = 'Avans Tahsilatı'

    # ------------------------------------------------------------------
    # İşlem başlat
    # ------------------------------------------------------------------

    def action_send(self):
        self.ensure_one()
        if not self.terminal_id:
            raise UserError(_('Lütfen bir terminal seçin.'))
        if self.amount <= 0:
            raise UserError(_('Tutar sıfırdan büyük olmalıdır.'))

        order_no = self.order_no or str(uuid.uuid4())[:16].replace('-', '')
        client = self.terminal_id._get_client()

        try:
            if self.sale_type == 'sale':
                result = self._do_sale_with_items(client, order_no)
            elif self.sale_type == 'advance':
                result = self._do_advance_sale(client, order_no)
            else:
                result = self._do_current_sale(client, order_no)
        except Exception as exc:
            raise UserError(_('Pavo isteği başarısız: %s') % exc)

        txn = self._create_transaction(order_no, result)
        txn._apply_result(result)

        self.write({
            'result_state': 'success' if txn.state == 'success' else 'pending',
            'result_message': _('İşlem iletildi. Satış No: %s') % (txn.sale_number or order_no),
            'transaction_id': txn.id,
        })
        return self._reopen()

    def _do_sale_with_items(self, client, order_no):
        inv = self.invoice_id
        items = []
        if inv:
            for line in inv.invoice_line_ids.filtered(lambda l: not l.display_type):
                price_unit = line.price_unit
                qty = line.quantity
                gross = round(price_unit * qty, 2)
                net = round(line.price_subtotal, 2)
                tax_code = self._tax_group_code(line)
                items.append({
                    'Name': line.name or line.product_id.name or 'Ürün',
                    'Barcode': line.product_id.barcode or '',
                    'IsGeneric': not bool(line.product_id.barcode),
                    'UnitCode': 'C62',
                    'TaxGroupCode': tax_code,
                    'ItemQuantity': qty,
                    'UnitPriceAmount': price_unit,
                    'GrossPriceAmount': gross,
                    'TotalPriceAmount': net,
                })
        if not items:
            items = [{
                'Name': self.sale_reason or 'Ürün',
                'IsGeneric': True,
                'UnitCode': 'C62',
                'TaxGroupCode': 'KDV20',
                'ItemQuantity': 1,
                'UnitPriceAmount': self.amount,
                'GrossPriceAmount': self.amount,
                'TotalPriceAmount': self.amount,
            }]

        gross_total = round(sum(i['GrossPriceAmount'] for i in items), 2)
        net_total = round(sum(i['TotalPriceAmount'] for i in items), 2)

        return client.start_sale_with_items(
            items=items,
            gross_price=gross_total,
            total_price=net_total,
            order_no=order_no,
            main_document_type=int(self.main_document_type),
            currency_code=self.currency_code if self.currency_code != 'TRY' else None,
        )

    def _do_advance_sale(self, client, order_no):
        invoice_data = self._build_invoice_data()
        return client.advance_sale(
            total_amount=self.amount,
            sale_reason=self.sale_reason or 'Avans',
            order_no=order_no,
            invoice_data=invoice_data or None,
            currency_code=self.currency_code if self.currency_code != 'TRY' else None,
        )

    def _do_current_sale(self, client, order_no):
        invoice_data = self._build_invoice_data()
        if not invoice_data:
            raise UserError(_(
                'Cari ödeme için fatura bilgisi zorunludur. '
                'Lütfen bir fatura seçin veya Avans Ödeme tipini kullanın.'))
        return client.current_sale(
            total_amount=self.amount,
            sale_reason=self.sale_reason or 'Cari Tahsilat',
            invoice_data=invoice_data,
            order_no=order_no,
            currency_code=self.currency_code if self.currency_code != 'TRY' else None,
        )

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _build_invoice_data(self):
        if not self.invoice_id or not self.invoice_id.name:
            return []
        inv = self.invoice_id
        date_str = (inv.invoice_date or inv.date or fields.Date.today()).strftime('%Y-%m-%d')
        return [{'InvoiceNo': inv.name, 'InvoiceDate': date_str}]

    @staticmethod
    def _tax_group_code(line):
        """KDV oranından Pavo TaxGroupCode türet."""
        for tax in line.tax_ids:
            amount = abs(tax.amount)
            if amount == 20:
                return 'KDV20'
            if amount == 10:
                return 'KDV10'
            if amount == 1:
                return 'KDV1'
            if amount == 0:
                return 'KDV0'
        return 'KDV20'

    def _create_transaction(self, order_no, result):
        sale = result.get('Sale') or result.get('Data') or {}
        return self.env['iber.pavo.transaction'].create({
            'terminal_id': self.terminal_id.id,
            'invoice_id': self.invoice_id.id if self.invoice_id else False,
            'sale_type': self.sale_type,
            'order_no': order_no,
            'sale_number': sale.get('SaleNumber'),
            'pavo_sale_id': sale.get('Id') or 0,
            'amount': self.amount,
            'currency_code': self.currency_code,
            'sale_reason': self.sale_reason,
            'response_json': json.dumps(result, ensure_ascii=False, indent=2),
            'state': 'pending',
        })

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_transaction(self):
        self.ensure_one()
        if not self.transaction_id:
            raise UserError(_('Henüz işlem kaydı oluşturulmadı.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'iber.pavo.transaction',
            'res_id': self.transaction_id.id,
            'view_mode': 'form',
            'target': 'new',
        }
