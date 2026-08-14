from odoo import models, fields


class UBL21ConfigSettingsSeriesExt(models.Model):
    """
    ubl21.config.settings'e varsayılan seri seçimi ekler.
    iber_edonusum kuruluysa aktif olur.
    """
    _inherit = "ubl21.config.settings"

    last_incoming_invoice_sync_datetime = fields.Datetime(
        string="Last Incoming Invoice Sync Time", readonly=True
    )

    default_invoice_series_id = fields.Many2one(
        "edn.invoice.series",
        string="Default Invoice Series",
        domain="[('document_type', 'in', ['invoice', 'earchive'])]",
        help="Default GIB series code (prefix) used for new UBL invoices",
    )
    default_despatch_series_id = fields.Many2one(
        "edn.invoice.series",
        string="Default Despatch Series",
        domain="[('document_type', '=', 'despatch')]",
        help="Default GIB series code (prefix) used for new UBL despatch advices",
    )

    def action_clear_incoming_invoice_sync_time(self):
        self.ensure_one()
        self.write({"last_incoming_invoice_sync_datetime": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Success",
                "message": "Incoming invoice sync time cleared. The last 30 days will be queried on the next fetch.",
                "type": "success",
                "sticky": False,
            },
        }
