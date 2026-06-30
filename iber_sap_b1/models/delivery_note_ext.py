from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class UBLDeliveryNoteSAPB1(models.Model):
    """
    SAP B1 senkronizasyonu için l10n_tr.ubl.delivery.note'u genişletir.
    action_sync_from_erp → sap_b1 seçiliyse bu sınıftaki mantık devreye girer.
    """
    _inherit = "l10n_tr.ubl.delivery.note"

    @api.model
    def action_sync_from_erp(self):
        settings = self.env["ubl21.config.settings"].get_singleton()
        if not settings:
            raise UserError("Ayarlar bulunamadı.")

        if settings.active_erp == "sap_b1":
            return self._sync_from_sap_b1(settings)

        return super().action_sync_from_erp()

    def _sync_from_sap_b1(self, settings):
        from .sap_b1_connector import SAPB1Connector
        from .sap_b1_mapper import SAPB1Mapper

        _logger.info("=== SAP B1 İrsaliye Senkronizasyonu Başlatıldı ===")

        if not settings.sap_service_layer_url:
            raise UserError("SAP B1 Service Layer URL tanımlı değil.")

        connector = SAPB1Connector(settings, env=self.env)
        mapper = SAPB1Mapper(self.env)
        last_sync = settings.last_delivery_note_sync_datetime
        sync_start_time = fields.Datetime.now()
        created_count = updated_count = error_count = 0

        with connector:
            _logger.info("SAP B1'e bağlanılıyor...")
            sap_dns = connector.fetch_delivery_notes(erp_status="0", last_sync_datetime=last_sync)
            _logger.info("SAP B1'den %d irsaliye çekildi", len(sap_dns))

            for sap_dn in sap_dns:
                try:
                    doc_entry = str(sap_dn.get("DocEntry"))
                    existing = self.search([
                        ("erp_id", "=", doc_entry),
                        ("erp_object_type", "=", mapper.get_delivery_note_object_type()),
                    ], limit=1)
                    header_vals = mapper.map_delivery_note_header(sap_dn, connector=connector)
                    header_vals["erp_last_sync_date"] = fields.Datetime.now()
                    if existing:
                        existing.write(header_vals)
                        self._sap_sync_dn_lines(existing, sap_dn, mapper, connector)
                        updated_count += 1
                    else:
                        new_dn = self.create(header_vals)
                        self._sap_sync_dn_lines(new_dn, sap_dn, mapper, connector)
                        created_count += 1
                except Exception as e:
                    error_count += 1
                    _logger.error("İrsaliye %s işlenirken hata: %s", sap_dn.get("DocEntry"), str(e))

        settings.write({"last_delivery_note_sync_datetime": sync_start_time})

        message = (
            f"SAP B1 İrsaliye Senkronizasyonu tamamlandı.\n"
            f"Oluşturulan: {created_count}\n"
            f"Güncellenen: {updated_count}"
        )
        if error_count:
            message += f"\nHata: {error_count}"

        _logger.info("=== SAP B1 İrsaliye Senkronizasyonu Tamamlandı: +%d =%d !%d ===",
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

    def _sap_sync_dn_lines(self, delivery_note, sap_dn, mapper, connector):
        delivery_note.line_ids.unlink()
        sap_lines = sap_dn.get("DocumentLines", [])
        for idx, sap_line in enumerate(sap_lines, start=1):
            line_vals = mapper.map_delivery_note_line(sap_line, idx, connector=connector)
            line_vals["base_document_id"] = delivery_note.base_document_id.id
            self.env["l10n_tr.ubl.delivery.note.line"].create(line_vals)
        _logger.debug("İrsaliye %s için %d satır senkronize edildi", delivery_note.id_value, len(sap_lines))
