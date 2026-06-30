from odoo import models, fields, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    iber_pavo_transaction_ids = fields.One2many(
        'iber.pavo.transaction', 'invoice_id', string='Pavo İşlemleri')
    iber_pavo_transaction_count = fields.Integer(
        compute='_compute_pavo_count', string='Pavo İşlem Sayısı')

    def _compute_pavo_count(self):
        for rec in self:
            rec.iber_pavo_transaction_count = len(rec.iber_pavo_transaction_ids)

    def action_pavo_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pavo ile Ödeme Al'),
            'res_model': 'iber.pavo.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_invoice_id': self.id,
                'default_amount': self.amount_residual,
            },
        }

    def action_view_pavo_transactions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pavo İşlemleri'),
            'res_model': 'iber.pavo.transaction',
            'view_mode': 'list,form',
            'domain': [('invoice_id', '=', self.id)],
        }
