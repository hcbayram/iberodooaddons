# -*- coding: utf-8 -*-
"""
iber_edonusum — İrsaliye Entegratör Senkronizasyonu

Gelen irsaliyeler : entegratör → l10n_tr.ubl.delivery.note (incoming)
Durum çevirisi entegratör client'ının status_map'inden yapılır.
"""
import logging
from datetime import datetime, timedelta, timezone
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _parse_nes_date(val):
    if not val:
        return False
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(val[:len(fmt) + 3], fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(val[:19]).date()
    except Exception:
        return False


def _map_incoming_despatch(item, env, client=None):
    """İrsaliye item dict'ini l10n_tr.ubl.delivery.note vals'ına çevirir."""
    xh = item.get("_xml_header") or {}
    xml_supplier = (xh.get("supplier") or {})

    uuid = str(item.get("id") or item.get("uuid") or "").strip()
    doc_number = (
        item.get("despatchNumber") or item.get("documentNumber") or
        xh.get("id") or uuid[:16]
    )
    issue_date = _parse_nes_date(item.get("issueDate") or xh.get("issueDate"))

    # Gönderici (supplier)
    supplier_vkn = (
        xml_supplier.get("taxNumber") or
        (item.get("accountingSupplierParty") or {}).get("partyIdentification") or ""
    )
    supplier_name = (
        xml_supplier.get("name") or
        (item.get("accountingSupplierParty") or {}).get("partyName") or "—"
    )

    # Durum
    raw_status = (item.get("documentStatus") or "").upper()
    gib_status = client.translate_status(raw_status) if client else "sent"

    # Envelope
    envelope_obj = item.get("incomingEnvelope") or {}
    envelope_id = envelope_obj.get("envelopeId") or item.get("envelopeId") or ""
    send_date = _parse_nes_date(
        envelope_obj.get("createdAt") or item.get("createdAt")
    )

    import json
    item_clean = {k: v for k, v in item.items() if not k.startswith("_")}
    xml_data_str = item.get("_xml_data") or ""

    vals = {
        "document_direction": "incoming",
        "UUID": uuid,
        "id_value": doc_number or uuid or "/",
        "issue_date": issue_date or fields.Date.today(),
        "supplier_name": supplier_name,
        "supplier_vkn_tckn": supplier_vkn,
        "gib_status": gib_status,
        "gib_envelope_id": envelope_id or False,
        "gib_send_date": send_date or False,
        "erp_last_sync_date": fields.Datetime.now(),
    }
    if xml_data_str:
        vals["xml_data"] = xml_data_str
    return vals


class DeliveryNoteIntegratorSync(models.Model):
    _inherit = "l10n_tr.ubl.delivery.note"

    @api.model
    def action_fetch_incoming_from_integrator(self, ids=None, ui_filters=None):
        """
        Gelen irsaliyeleri NES'ten çeker ve yerel DB'ye kaydeder.
        Liste üstündeki 'Entegratörden İrsaliyeleri Getir' butonu tarafından çağrılır.
        """
        ui_filters = ui_filters or {}
        settings = self.env["ubl21.config.settings"].get_singleton()
        if not settings or not settings.integrator_id:
            raise UserError(_("No active integrator is defined in settings."))
        integrator_code = settings.integrator_id.code
        mgr = self.env["edn.document.manager"].sudo()
        client = mgr._get_integrator_client(integrator_code)

        today = fields.Date.today()
        today_str = today.strftime("%Y-%m-%d")

        date_ranges = []
        if ui_filters.get("startCreateDate"):
            date_ranges.append((
                ui_filters["startCreateDate"][:10],
                (ui_filters.get("endCreateDate") or today_str)[:10],
            ))
        else:
            last_sync = getattr(settings, "last_delivery_note_sync_datetime", None)
            if last_sync:
                last_sync_date = last_sync.date() if hasattr(last_sync, "date") else last_sync
                diff = (today - last_sync_date).days
                if diff < 1:
                    diff = 30
                start_dt = today - timedelta(days=diff)
                # 30 günlük parçalara böl
                chunk_start = start_dt
                while chunk_start < today:
                    chunk_end = min(chunk_start + timedelta(days=29), today)
                    date_ranges.append((
                        chunk_start.strftime("%Y-%m-%d"),
                        chunk_end.strftime("%Y-%m-%d"),
                    ))
                    chunk_start = chunk_end + timedelta(days=1)
            else:
                start_30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                date_ranges.append((start_30, today_str))

        all_items = []
        for start_str, end_str in date_ranges:
            filters = {
                "document_type": "despatch",
                "include_lines": True,
                "startCreateDate": start_str,
                "endCreateDate": end_str,
            }
            _logger.info("Gelen irsaliye çekiliyor: %s → %s", start_str, end_str)
            result = self.env["edn.document.manager"].get_incoming_documents(
                integrator_code, filters, client=client
            )
            if not result.get("ok"):
                raise UserError(
                    _("Could not fetch data from integrator (%s→%s):\n%s") % (
                        start_str, end_str, result.get("error", "Unknown error")
                    )
                )
            items = result.get("documents") or []
            if not items:
                raw = result.get("raw")
                if isinstance(raw, list):
                    items = raw
                elif isinstance(raw, dict):
                    items = (
                        raw.get("items") or raw.get("data") or
                        raw.get("documents") or raw.get("despatches") or
                        raw.get("results") or []
                    )
            all_items.extend(items)

        _logger.info("Toplam %d irsaliye alındı", len(all_items))
        created = updated = skipped = errors = 0

        for item in all_items:
            try:
                uuid = str(item.get("id") or item.get("uuid") or item.get("UUID") or "").strip()
                if not uuid:
                    skipped += 1
                    continue

                vals = _map_incoming_despatch(item, self.env, client=client)
                existing = self.search([
                    ("UUID", "=", uuid),
                    ("document_direction", "=", "incoming"),
                ], limit=1)

                if existing:
                    existing.sudo().write(vals)
                    updated += 1
                else:
                    self.sudo().create(vals)
                    created += 1
            except Exception as e:
                _logger.error("İrsaliye kaydedilemedi (uuid=%s): %s", item.get("id", "?"), e)
                errors += 1

        # Son sync zamanını güncelle
        if hasattr(settings, "last_delivery_note_sync_datetime"):
            settings.sudo().write({"last_delivery_note_sync_datetime": fields.Datetime.now()})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Despatch Sync Completed"),
                "message": _(
                    "New: %d  |  Updated: %d  |  Skipped: %d  |  Errors: %d"
                ) % (created, updated, skipped, errors),
                "type": "success" if not errors else "warning",
                "sticky": True,
            },
        }

    def action_fetch_single_incoming(self):
        """Form butonuyla tek bir gelen irsaliyeyi NES'ten günceller."""
        self.ensure_one()
        if not self.UUID:
            raise UserError(_("No UUID found on this despatch advice."))

        settings = self.env["ubl21.config.settings"].get_singleton()
        integrator_code = settings.integrator_id.code if settings.integrator_id else None
        if not integrator_code:
            raise UserError(_("No active integrator is defined in settings."))

        mgr = self.env["edn.document.manager"].sudo()
        client = mgr._get_integrator_client(integrator_code)
        xml_result = client.get_despatch_lines(self.UUID)
        if not xml_result.get("ok"):
            raise UserError(
                _("Could not fetch XML:\n%s") % xml_result.get("error", "Unknown error")
            )

        raw = xml_result.get("raw") or {}
        xml_header = raw.get("header") or {}

        fake_item = {
            "id": self.UUID,
            "despatchNumber": xml_header.get("id") or self.id_value,
            "issueDate": xml_header.get("issueDate"),
            "_xml_header": xml_header,
        }

        vals = _map_incoming_despatch(fake_item, self.env, client=client)
        xml_clean = raw.get("xml_clean") or ""
        if xml_clean:
            vals["xml_data"] = xml_clean

        try:
            self.sudo().write(vals)
        except Exception as e:
            _logger.error("İrsaliye write hatası: %s", e)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Despatch Advice Updated"),
                "message": _("Despatch advice %s updated from %s.") % (self.id_value, integrator_code),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "l10n_tr.ubl.delivery.note",
                    "res_id": self.id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "target": "current",
                },
            },
        }
