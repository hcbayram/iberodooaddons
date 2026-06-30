from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class UBLInvoiceSAPB1(models.Model):
    """
    SAP B1 senkronizasyonu için l10n_tr.ubl.invoice'ı genişletir.
    action_sync_from_erp → sap_b1 seçiliyse bu sınıftaki mantık devreye girer.
    """
    _inherit = "l10n_tr.ubl.invoice"

    @api.model
    def action_sync_from_erp(self):
        settings = self.env["ubl21.config.settings"].get_singleton()
        if not settings:
            raise UserError("Ayarlar bulunamadı.")

        if settings.active_erp == "sap_b1":
            return self._sync_from_sap_b1(settings)

        # Diğer ERP'ler için üst sınıfa devret
        return super().action_sync_from_erp()

    def _sync_from_sap_b1(self, settings):
        from .sap_b1_connector import SAPB1Connector
        from .sap_b1_mapper import SAPB1Mapper

        _logger.info("=== SAP B1 Fatura Senkronizasyonu Başlatıldı ===")

        if not settings.sap_service_layer_url:
            raise UserError("SAP B1 Service Layer URL tanımlı değil. Lütfen SAP B1 bağlantı ayarlarını yapılandırın.")

        connector = SAPB1Connector(settings, env=self.env)
        mapper = SAPB1Mapper(self.env)
        last_sync = settings.last_invoice_sync_datetime
        sync_start_time = fields.Datetime.now()
        created_count = updated_count = error_count = 0

        with connector:
            _logger.info("SAP B1'e bağlanılıyor...")
            sap_invoices = connector.fetch_invoices(erp_status="0", last_sync_datetime=last_sync)
            _logger.info("SAP B1'den %d fatura çekildi", len(sap_invoices))

            for sap_invoice in sap_invoices:
                try:
                    sap_doc_entry = str(sap_invoice.get("DocEntry"))
                    existing = self.search([
                        ("erp_id", "=", sap_doc_entry),
                        ("erp_object_type", "=", mapper.get_invoice_object_type()),
                    ], limit=1)
                    header_vals = mapper.map_invoice_header(sap_invoice, connector=connector)
                    header_vals["erp_last_sync_date"] = fields.Datetime.now()
                    if existing:
                        existing.write(header_vals)
                        self._sap_sync_invoice_lines(existing, sap_invoice, mapper, connector)
                        updated_count += 1
                    else:
                        new_inv = self.create(header_vals)
                        self._sap_sync_invoice_lines(new_inv, sap_invoice, mapper, connector)
                        created_count += 1
                except Exception as e:
                    error_count += 1
                    _logger.error("Fatura %s işlenirken hata: %s", sap_invoice.get("DocEntry"), str(e))

        settings.write({"last_invoice_sync_datetime": sync_start_time})

        message = (
            f"SAP B1 Fatura Senkronizasyonu tamamlandı.\n"
            f"Oluşturulan: {created_count}\n"
            f"Güncellenen: {updated_count}"
        )
        if error_count:
            message += f"\nHata: {error_count}"

        _logger.info("=== SAP B1 Fatura Senkronizasyonu Tamamlandı: +%d =%d !%d ===",
                     created_count, updated_count, error_count)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("SAP B1 Senkronizasyonu Tamamlandı"),
                "message": message,
                "type": "success" if not error_count else "warning",
                "sticky": False,
            },
        }

    def _sap_sync_invoice_lines(self, invoice, sap_invoice, mapper, connector):
        invoice.line_ids.unlink()
        sap_lines = sap_invoice.get("DocumentLines", [])
        line_commands = []
        for idx, sap_line in enumerate(sap_lines, start=1):
            line_vals = mapper.map_invoice_line(
                sap_invoice.get("DocType"), sap_line, idx, connector=connector
            )
            line_commands.append((0, 0, line_vals))
        if line_commands:
            invoice.write({"line_ids": line_commands})
        _logger.debug("Fatura %s için %d satır senkronize edildi", invoice.id_value, len(sap_lines))
