from odoo import models, fields


class UBL21ConfigSettingsSeriesExt(models.Model):
    """
    ubl21.config.settings'e varsayılan seri seçimi ekler.
    iber_edonusum kuruluysa aktif olur.
    """
    _inherit = "ubl21.config.settings"

    last_incoming_invoice_sync_datetime = fields.Datetime(
        string="Son Gelen Fatura Senkronizasyon Zamanı", readonly=True
    )

    default_invoice_series_id = fields.Many2one(
        "edn.invoice.series",
        string="Varsayılan Fatura Serisi",
        domain="[('document_type', 'in', ['invoice', 'earchive'])]",
        help="Yeni UBL faturalarında kullanılacak varsayılan GIB seri kodu (prefix)",
    )
    default_despatch_series_id = fields.Many2one(
        "edn.invoice.series",
        string="Varsayılan İrsaliye Serisi",
        domain="[('document_type', '=', 'despatch')]",
        help="Yeni UBL irsaliyelerinde kullanılacak varsayılan GIB seri kodu (prefix)",
    )

    def action_clear_incoming_invoice_sync_time(self):
        self.ensure_one()
        self.write({"last_incoming_invoice_sync_datetime": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Başarılı",
                "message": "Gelen fatura senkronizasyon zamanı temizlendi. Bir sonraki getirmede son 30 gün sorgulanacak.",
                "type": "success",
                "sticky": False,
            },
        }
