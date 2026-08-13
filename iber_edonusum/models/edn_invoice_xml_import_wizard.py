# -*- coding: utf-8 -*-
"""
Gelen e-Faturayı ham UBL-TR XML'inden elle içe aktarma sihirbazı.

Kullanım amacı: paylaşımlı bir test entegratör hesabında "Web Servisden
Alındı" gibi bir bayrak başka test kullanıcıları tarafından değiştirildiği
için istenen belge entegratör inbox listesinden artık çekilemiyor olabilir.
Bu durumda, belgenin ham XML'i (destek ekibinden/portaldan) elde edilip
doğrudan buradan içe aktarılabilir — entegratör API'sine hiç bağımlı
kalmadan.
"""
import base64
import logging
import uuid as uuid_lib

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .invoice_integrator_sync import _map_incoming_invoice, _create_invoice_lines
from ..core.ubl_xml_parser import parse_incoming_ubl_xml

_logger = logging.getLogger(__name__)


class EdnInvoiceXmlImportWizard(models.TransientModel):
    _name = "edn.invoice.xml.import.wizard"
    _description = "Gelen e-Fatura: XML'den İçe Aktar"

    xml_file = fields.Binary("UBL-TR XML Dosyası", required=True)
    xml_filename = fields.Char("Dosya Adı")

    def action_import(self):
        self.ensure_one()
        try:
            xml_text = base64.b64decode(self.xml_file).decode("utf-8")
        except Exception as exc:
            raise UserError(_("XML dosyası okunamadı/çözümlenemedi: %s") % exc)

        try:
            parsed = parse_incoming_ubl_xml(xml_text)
        except Exception as exc:
            raise UserError(_(
                "XML ayrıştırılamadı — geçerli bir UBL-TR fatura XML'i "
                "olduğundan emin olun.\nHata: %s"
            ) % exc)

        header = parsed.get("header") or {}
        lines_data = parsed.get("data") or []
        totals = parsed.get("documentTotals") or {}

        doc_uuid = header.get("uuid") or ""
        if not doc_uuid:
            # GİB UBL-TR'de cbc:UUID zorunludur — yoksa (ör. eksik/özel bir
            # test dosyası) rastgele bir UUID üretilir ki kayıt en azından
            # oluşturulabilsin; ancak bu durumda entegratör tabanlı
            # dedup/eşleme ile bağlantı kurulamayacağı loglanır.
            doc_uuid = str(uuid_lib.uuid4())
            _logger.warning(
                "İçe aktarılan XML'de cbc:UUID bulunamadı, rastgele UUID "
                "üretildi: %s (belge no: %s)", doc_uuid, header.get("id"),
            )

        existing = self.env["l10n_tr.ubl.invoice"].search([
            ("UUID", "=", doc_uuid),
            ("invoice_direction", "=", "incoming"),
        ], limit=1)
        if existing:
            raise UserError(_(
                "Bu belge zaten sistemde mevcut (Belge No: %s, UUID: %s)."
            ) % (existing.id_value, doc_uuid))

        fake_item = {
            "id": doc_uuid,
            "documentNumber": header.get("id"),
            "issueDate": header.get("issueDate"),
            "profileId": header.get("profileId"),
            "invoiceTypeCode": header.get("invoiceTypeCode"),
            "documentCurrencyCode": header.get("currencyCode") or totals.get("currencyID"),
            "_xml_header": header,
        }
        vals = _map_incoming_invoice(fake_item, self.env, client=None)
        vals["xml_data"] = xml_text

        new_inv = self.env["l10n_tr.ubl.invoice"].create(vals)
        if lines_data:
            _create_invoice_lines(new_inv, lines_data, self.env)

        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n_tr.ubl.invoice",
            "res_id": new_inv.id,
            "view_mode": "form",
            "target": "current",
        }
