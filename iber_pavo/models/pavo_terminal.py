import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberPavoTerminal(models.Model):
    _name = 'iber.pavo.terminal'
    _description = 'Pavo POS Terminal'
    _rec_name = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    ip_address = fields.Char(string='IP Adresi', required=True)
    use_ssl = fields.Boolean(string='HTTPS (Güvenli)', default=True)
    port = fields.Integer(compute='_compute_port', string='Port', store=False)

    serial_number = fields.Char(string='Seri No', readonly=True, copy=False)
    fingerprint = fields.Char(string='Fingerprint', copy=False)
    transaction_sequence = fields.Integer(
        string='İşlem Sırası', default=0, readonly=True, copy=False)

    referer_app = fields.Char(
        string='Uygulama Adı', default='IberOdoo', required=True)
    referer_app_version = fields.Char(
        string='Uygulama Versiyonu', default='19.0.1.0.0', required=True)

    state = fields.Selection([
        ('draft', 'Eşleştirilmedi'),
        ('paired', 'Eşleştirildi'),
        ('error', 'Hata'),
    ], default='draft', readonly=True)
    last_error = fields.Text(string='Son Hata', readonly=True)

    transaction_ids = fields.One2many(
        'iber.pavo.transaction', 'terminal_id', string='İşlemler')
    transaction_count = fields.Integer(compute='_compute_transaction_count')

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    @api.depends('use_ssl')
    def _compute_port(self):
        for rec in self:
            rec.port = 4567 if rec.use_ssl else 4568

    @api.depends('transaction_ids')
    def _compute_transaction_count(self):
        for rec in self:
            rec.transaction_count = len(rec.transaction_ids)

    # ------------------------------------------------------------------
    # API client
    # ------------------------------------------------------------------

    def _get_client(self):
        self.ensure_one()
        from ..core.pavo_client import PavoClient

        def _on_sequence_update(new_seq):
            self.sudo().write({'transaction_sequence': new_seq})

        return PavoClient(
            ip=self.ip_address,
            use_ssl=self.use_ssl,
            serial_number=self.serial_number or '',
            fingerprint=self.fingerprint or '',
            transaction_sequence=self.transaction_sequence,
            referer_app=self.referer_app,
            referer_app_version=self.referer_app_version,
            on_sequence_update=_on_sequence_update,
        )

    # ------------------------------------------------------------------
    # Aksiyonlar
    # ------------------------------------------------------------------

    def action_pair(self):
        self.ensure_one()
        if not self.fingerprint:
            raise UserError(_('Eşleştirme için önce Fingerprint alanını doldurun.'))
        try:
            client = self._get_client()
            result = client.pair()
            handle = result.get('TransactionHandle', {})
            self.write({
                'serial_number': handle.get('SerialNumber', self.serial_number),
                'fingerprint': handle.get('Fingerprint', self.fingerprint),
                'transaction_sequence': handle.get('TransactionSequence', 1),
                'state': 'paired',
                'last_error': False,
            })
            return self._notify(_('Cihaz başarıyla eşleştirildi.'), 'success')
        except Exception as exc:
            self.write({'state': 'error', 'last_error': str(exc)})
            raise UserError(_('Eşleştirme hatası: %s') % exc)

    def action_ping(self):
        self.ensure_one()
        try:
            client = self._get_client()
            client.ping()
            return self._notify(_('Cihaza bağlantı başarılı (Ping OK).'), 'success')
        except Exception as exc:
            self.write({'state': 'error', 'last_error': str(exc)})
            raise UserError(_('Ping hatası: %s') % exc)

    def action_view_transactions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('İşlemler'),
            'res_model': 'iber.pavo.transaction',
            'view_mode': 'list,form',
            'domain': [('terminal_id', '=', self.id)],
            'context': {'default_terminal_id': self.id},
        }

    @staticmethod
    def _notify(message, msg_type='info'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': message, 'type': msg_type, 'sticky': False},
        }
