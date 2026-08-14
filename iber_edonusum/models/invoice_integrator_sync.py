# -*- coding: utf-8 -*-
"""
iber_edonusum — Fatura Entegratör Senkronizasyonu

Gelen faturalar : entegratör → l10n_tr.ubl.invoice (incoming)
Giden faturalar : Odoo'dan senkronize et.

Durum çevirisi entegratör client'ının status_map/answer_map'inden yapılır;
bu dosyada NES'e özgü map tanımlanmaz.
"""
import base64
import logging
from datetime import datetime, timedelta, timezone
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _parse_nes_date(val):
    """NES tarih string'ini date nesnesine çevirir."""
    if not val:
        return None
    try:
        if "T" in str(val):
            return datetime.strptime(str(val).split(".")[0], "%Y-%m-%dT%H:%M:%S").date()
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_nes_datetime(val):
    """NES datetime string'ini naive UTC datetime'a çevirir."""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        try:
            if "T" in str(val):
                return datetime.strptime(str(val).split(".")[0], "%Y-%m-%dT%H:%M:%S")
            return datetime.strptime(str(val)[:10], "%Y-%m-%d")
        except Exception:
            return None


def _map_incoming_invoice(item: dict, env, client=None) -> dict:
    """
    Gelen fatura dict'ini l10n_tr.ubl.invoice create/write vals'ına çevirir.
    client: IntegratorBase instance — durum çevirisi için kullanılır.
    """
    def _get(*keys, default=""):
        for k in keys:
            v = item.get(k)
            if v is not None and v != "":
                return v
        return default

    # XML başlık verisi (include_lines=True ile gelen)
    xh = item.get("_xml_header") or {}
    xml_supplier = xh.get("supplier") or {}
    xml_customer = xh.get("customer") or {}

    # Odoo 17 referans: id → ETTN/UUID, documentNumber → fatura no
    uuid         = _get("id", "uuid", "UUID")
    doc_number   = (xh.get("id") or _get("documentNumber", "invoiceNumber", "docNumber"))
    issue_date   = _parse_nes_date(xh.get("issueDate") or _get("issueDate", "invoiceDate"))
    profile_code  = (xh.get("profileId") or _get("profileId", "invoiceProfile", "profile"))
    doc_type_code = (xh.get("invoiceTypeCode") or _get("invoiceTypeCode", "documentType", "invoiceType"))
    currency_code = (xh.get("currencyCode") or _get("documentCurrencyCode", "currencyCode", default="TRY"))

    # Gönderici: önce XML, sonra JSON liste yanıtı
    api_supplier  = item.get("accountingSupplierParty") or {}
    supplier_vkn  = (xml_supplier.get("taxNumber") or
                     api_supplier.get("partyIdentification") or
                     _get("senderIdentifier", "senderVKN", "senderTaxNumber"))
    supplier_name = (xml_supplier.get("name") or xml_supplier.get("personName") or
                     api_supplier.get("partyName") or
                     _get("senderTitle", "senderName", "senderCompanyName"))
    supplier_tax_office = xml_supplier.get("taxOfficeName") or ""
    supplier_street     = xml_supplier.get("streetName") or ""
    supplier_city       = xml_supplier.get("cityName") or ""
    supplier_county     = xml_supplier.get("district") or xml_supplier.get("citySubdivision") or ""
    supplier_postal     = xml_supplier.get("postalZone") or ""
    supplier_country    = xml_supplier.get("countryCode") or "TR"

    # Alıcı: önce XML, sonra JSON liste yanıtı
    api_customer  = item.get("accountingCustomerParty") or {}
    customer_name = (xml_customer.get("name") or xml_customer.get("personName") or
                     api_customer.get("partyName") or
                     _get("receiverTitle", "receiverName", "receiverCompanyName"))
    customer_vkn  = (xml_customer.get("taxNumber") or
                     api_customer.get("partyIdentification") or
                     _get("receiverVKN", "receiverIdentifier", "receiverTaxNumber"))

    # Zarf & durum bilgisi
    incoming_envelope = item.get("incomingEnvelope") or {}
    nes_status_raw = str(_get("status", "documentStatus", "invoiceStatus") or "").upper()
    gib_status     = client.translate_status(nes_status_raw) if client else "sent"

    envelope_id   = (incoming_envelope.get("instanceIdentifier") or
                     _get("envelopeId", "envelopeNumber", "envelopeID"))
    send_date     = _parse_nes_datetime(
                        incoming_envelope.get("createdAt") or _get("createdAt", "sendDate"))
    response_date = _parse_nes_datetime(_get("responseDate", "answerDate"))
    response_note = (incoming_envelope.get("description") or
                     _get("responseNote", "answerNote", "note"))
    receiver_alias = _get("receiverAlias", "receiverLabel")

    # Profile → Many2one lookup
    profile_id = False
    if profile_code:
        p = env["algebra.base.document.profile.id"].search([("code", "=", profile_code)], limit=1)
        if not p:
            p = env["algebra.base.document.profile.id"].search([("code", "=", "TEMELFATURA")], limit=1)
        profile_id = p.id if p else False

    # Document type → Many2one lookup
    doc_type_id = False
    if doc_type_code:
        dt = env["algebra.base.document.type"].search([("code", "=", doc_type_code)], limit=1)
        doc_type_id = dt.id if dt else False
    if not doc_type_id:
        dt = env["algebra.base.document.type"].search([("code", "=", "SATIS")], limit=1)
        doc_type_id = dt.id if dt else False

    # Para birimi → Many2one lookup
    currency_id = False
    if currency_code:
        cur = env["res.currency"].search([("name", "=", currency_code)], limit=1)
        currency_id = cur.id if cur else False
    if not currency_id:
        ref = env.ref("base.TRY", raise_if_not_found=False)
        currency_id = ref.id if ref else False

    # Gönderici scheme: 10 hane → VKN, 11 hane → TCKN
    _svkn = str(supplier_vkn or "").replace(" ", "")
    supplier_scheme = "VKN" if len(_svkn) == 10 else ("TCKN" if len(_svkn) == 11 else "VKN")

    xml_data_str = item.get("_xml_data") or ""

    vals = {
        "invoice_direction": "incoming",
        "UUID": uuid,
        "id_value": doc_number or uuid or "/",
        "issue_date": issue_date or fields.Date.today(),
        # Gönderici
        "supplier_name": supplier_name or "—",
        "supplier_vkn_tckn": supplier_vkn or "",
        "supplier_scheme_id": supplier_scheme,
        "supplier_tax_office": supplier_tax_office or False,
        "supplier_street": supplier_street or False,
        "supplier_city": supplier_city or False,
        "supplier_county": supplier_county or False,
        "supplier_postal_code": supplier_postal or False,
        "supplier_country_code": supplier_country or "TR",
        "supplier_country_name": "TÜRKİYE" if (supplier_country or "TR") == "TR" else (supplier_country or "TR"),
        # Alıcı
        "customer_name": customer_name or env.company.name or "—",
        "customer_vkn_tckn": customer_vkn or env.company.vat or "",
        "customer_scheme_id": "VKN",
        "customer_country_code": "TR",
        "customer_country_name": "TÜRKİYE",
        # GIB/Durum
        "gib_status": gib_status,
        "gib_envelope_id": envelope_id or False,
        "gib_send_date": send_date or False,
        "gib_response_date": response_date or False,
        "gib_response_desc": response_note or False,
        "customer_receiver_alias": receiver_alias or False,
        # Senkronizasyon
        "erp_last_sync_date": fields.Datetime.now(),
    }
    if xml_data_str:
        vals["xml_data"] = xml_data_str
    if profile_id:
        vals["profile_id"] = profile_id
    if doc_type_id:
        vals["document_type_id"] = doc_type_id
    if currency_id:
        vals["document_currency_id"] = currency_id

    return vals


def _create_invoice_lines(invoice, lines_data, env):
    """
    NES kalem listesini l10n_tr.ubl.invoiceline kayıtlarına çevirir.
    Odoo 17 referans: gelen_efatura.py kalemleri_yukle() metodundan alınmıştır.
    """
    if not lines_data:
        return

    currency_id = invoice.document_currency_id.id if invoice.document_currency_id else False

    for idx, line in enumerate(lines_data, 1):
        try:
            _logger.info(
                "Kalem %d ham veri: discounts=%r taxExtras=%r percent=%r withholdingRate=%r withholdingCode=%r",
                idx, line.get("discounts"), line.get("taxExtras"), line.get("percent"),
                line.get("withholdingRate"), line.get("withholdingCode")
            )
            # Birim kodu — unit_code_id (Many2one) lookup
            unit_code_str = line.get("unitCode", "") or "NIU"
            unit = env["algebra.base.document.unit"].search(
                [("code", "=", unit_code_str)], limit=1
            )
            if not unit:
                unit = env["algebra.base.document.unit"].search(
                    [("code", "=", "NIU")], limit=1
                )

            # Tevkifat — withholding_code Selection alanı yalnızca tanımlı kodları kabul eder
            wh_code = (line.get("withholdingCode") or "").strip()
            valid_wh_codes = {"601", "602", "603", "604", "9015"}
            line_vals = {
                "base_document_id": invoice.id,
                "name": line.get("name") or "Ürün",
                "description": line.get("description") or "",
                "quantity": float(line.get("quantity") or 1.0),
                "unit_code_id": unit.id if unit else False,
                "price_amount": float(line.get("priceAmount") or 0.0),
                "tax_percent": float(line.get("percent") or 0.0),
                "tax_category_code": "S",
                "tax_scheme_code": "0015",
                "tax_scheme_name": "KDV",
                "currency_id": currency_id,
                "sellersItemId": line.get("sellersItemIdentification") or "",
                "withholding_rate": float(line.get("withholdingRate") or 0.0),
            }
            if wh_code in valid_wh_codes:
                line_vals["withholding_code"] = wh_code
            elif wh_code:
                _logger.warning(
                    "Bilinmeyen tevkifat kodu (fatura=%s, kalem=%d): %s",
                    invoice.id_value, idx, wh_code
                )
            new_line = env["l10n_tr.ubl.invoiceline"].create(line_vals)

            # Satır iskonto/arttırımları (cac:AllowanceCharge)
            # Entegratör XML'inde her AllowanceCharge kendi tutarıyla geliyor;
            # baz tutar verilmemişse satırın tam tutarı kullanılır (kademeli değil).
            line_full_amount = new_line.price_amount * new_line.quantity
            for disc in (line.get("discounts") or []):
                try:
                    # UBL'de MultiplierFactorNumeric kesir olarak gelir (0.01 = %1)
                    rate = float(disc.get("rate") or 0.0) * 100.0
                    amount = float(disc.get("amount") or 0.0)
                    base_amount = float(disc.get("baseAmount") or 0.0) or line_full_amount
                    if not rate and base_amount:
                        rate = (amount / base_amount) * 100.0 if base_amount else 0.0
                    env["l10n_tr.ubl.invoiceline.adjustment"].create({
                        "line_id": new_line.id,
                        "type": disc.get("type") or "discount",
                        "rate": rate,
                        "base_amount": base_amount,
                        "description": disc.get("description") or "",
                    })
                except Exception as de:
                    _logger.warning(
                        "İskonto oluşturma hatası (fatura=%s, kalem=%d): %s",
                        invoice.id_value, idx, str(de)
                    )

            # Diğer vergiler (ÖTV, Stopaj vb. — KDV dışındaki TaxSubtotal'lar)
            for extra in (line.get("taxExtras") or []):
                try:
                    code = (extra.get("code") or "").strip()
                    if not code:
                        continue
                    tax_type = env["l10n_tr.ubl.tax.type"].search([("code", "=", code)], limit=1)
                    if not tax_type:
                        _logger.warning(
                            "Bilinmeyen vergi kodu (fatura=%s, kalem=%d): %s",
                            invoice.id_value, idx, code
                        )
                        continue
                    # UBL'de Percent zaten yüzde olarak gelir (0.01 değil 1 gibi); MultiplierFactorNumeric değil
                    rate = float(extra.get("rate") or 0.0)
                    env["l10n_tr.ubl.invoiceline.taxextra"].create({
                        "line_id": new_line.id,
                        "tax_type_id": tax_type.id,
                        "rate": rate,
                    })
                except Exception as ee:
                    _logger.warning(
                        "Diğer vergi oluşturma hatası (fatura=%s, kalem=%d): %s",
                        invoice.id_value, idx, str(ee)
                    )
        except Exception as e:
            _logger.warning(
                "Kalem oluşturma hatası (fatura=%s, kalem=%d): %s",
                invoice.id_value, idx, str(e)
            )


class UBLInvoiceIntegratorSync(models.Model):
    _inherit = "l10n_tr.ubl.invoice"

    # ------------------------------------------------------------------
    # Gelen Faturalar: Entegratörden Getir
    # ------------------------------------------------------------------
    @api.model
    def action_fetch_incoming_from_integrator(self, ids=None, ui_filters=None):
        """
        Entegratörden gelen fatura listesini çekip l10n_tr.ubl.invoice kayıtlarına aktarır.
        ui_filters: JS tarafından gönderilen tarih filtreleri.

        Yalnızca UUID'si sistemde henüz bulunmayan (daha önce alınmamış)
        faturalar oluşturulur — sistemde zaten var olan bir fatura tekrar
        sorgulanıp üzerine yazılmaz (bkz. döngü içindeki gerekçe).
        """
        settings = self.env["ubl21.config.settings"].get_singleton()
        integrator_code = settings.integrator_id.code if settings.integrator_id else None
        if not integrator_code:
            raise UserError(
                "No active integrator is defined in settings.\n"
                "Fill in the IberoDoo → Settings → Integrator field."
            )
        mgr = self.env["edn.document.manager"].sudo()
        client = mgr._get_integrator_client(integrator_code)

        ui_filters = ui_filters or {}
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")

        # JS'den tarih filtresi geldiyse onu kullan, yoksa last_sync mantığı
        if ui_filters.get("startCreateDate") or ui_filters.get("startDate"):
            # JS filtresinden direkt tarih aralığı al
            start_str = (ui_filters.get("startCreateDate") or ui_filters.get("startDate") or "")[:10]
            end_str   = (ui_filters.get("endCreateDate")   or ui_filters.get("endDate")   or today_str)[:10]
            date_ranges = [(start_str, end_str)]
        else:
            # last_sync tabanlı otomatik aralık
            last_sync = getattr(settings, "last_incoming_invoice_sync_datetime", None)
            date_ranges = []
            if last_sync:
                start_dt = last_sync.replace(tzinfo=None)
                diff = (today - start_dt).days
                if diff < 1:
                    start_dt = today - timedelta(days=30)
                    diff = 30
                if diff > 30:
                    cur = start_dt
                    while cur < today:
                        nxt = min(cur + timedelta(days=30), today)
                        date_ranges.append((cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d")))
                        cur = nxt + timedelta(days=1)
                else:
                    date_ranges.append((start_dt.strftime("%Y-%m-%d"), today_str))
            else:
                start_30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                date_ranges.append((start_30, today_str))

        sync_start = fields.Datetime.now()
        all_items = []

        for start_str, end_str in date_ranges:
            filters = {
                "document_type": "invoice",
                "include_lines": True,
                "sort": "CreatedAt desc",
                "startCreateDate": start_str,
                "endCreateDate": end_str,
            }
            # JS'den startDate / endDate (fatura tarihi) geldiyse ekle
            if ui_filters.get("startDate"):
                filters["startDate"] = ui_filters["startDate"][:10]
            if ui_filters.get("endDate"):
                filters["endDate"] = ui_filters["endDate"][:10]
            _logger.info("Gelen fatura çekiliyor: %s → %s", start_str, end_str)
            result = self.env["edn.document.manager"].get_incoming_documents(
                integrator_code, filters, client=client
            )
            if not result.get("ok"):
                raise UserError(
                    f"Could not fetch data from integrator ({start_str}→{end_str}):\n"
                    f"{result.get('error', 'Unknown error')}"
                )
            # Entegratörler normalize "documents" listesi döndürür.
            # "raw" ham API yanıtı olup liste olabilir — üzerinde .get() çağrılmaz.
            items = result.get("documents") or []
            if not items:
                raw = result.get("raw")
                if isinstance(raw, list):
                    items = raw
                elif isinstance(raw, dict):
                    items = (
                        raw.get("items") or raw.get("data") or
                        raw.get("documents") or raw.get("invoices") or
                        raw.get("results") or []
                    )
            all_items.extend(items)

        _logger.info("Toplam %d fatura alındı", len(all_items))
        if all_items:
            first = all_items[0]
            _logger.info("İlk item keys: %s", list(first.keys()))
            _logger.info("İlk item uuid/id: id=%r uuid=%r", first.get("id"), first.get("uuid"))
            raw = first.get("raw") or {}
            _logger.info("Ham item keys: %s", list(raw.keys()) if isinstance(raw, dict) else raw)

        created = skipped = errors = 0

        for item in all_items:
            try:
                status = self._import_incoming_item(item, client)
                if status == "created":
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                _logger.error("Gelen fatura işlenirken hata: %s", str(e), exc_info=True)

        settings.write({"last_incoming_invoice_sync_datetime": sync_start})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Invoices Fetched from Integrator"),
                "message": _(
                    "%(total)d invoice(s) evaluated.\n"
                    "New: %(c)d  |  Already in system (skipped): %(s)d  |  Errors: %(e)d"
                ) % {"total": created + skipped + errors,
                     "c": created, "s": skipped, "e": errors},
                "type": "success" if not errors else "warning",
                "sticky": True,
            },
        }

    def _import_incoming_item(self, item, client):
        """Tek bir entegratör item'ını l10n_tr.ubl.invoice kaydına çevirir.

        Sistemde UUID'si zaten bulunan bir belge varsa dokunulmadan atlanır
        (bkz. action_fetch_incoming_from_integrator'daki gerekçe — burada
        tekrarlanmıyor). Dönüş: "created" | "skipped".
        """
        uuid = str(item.get("id") or item.get("uuid") or item.get("UUID") or "").strip()
        if not uuid:
            return "skipped"

        existing = self.search([
            ("UUID", "=", uuid),
            ("invoice_direction", "=", "incoming"),
        ], limit=1)
        if existing:
            return "skipped"

        lines_data = item.get("lines") or []

        # Satır verisi yoksa XML çekip doldur (Hızlı gibi liste'de satır vermeyen entegratörler)
        if not lines_data and hasattr(client, "get_invoice_lines"):
            try:
                xl = client.get_invoice_lines(uuid)
                if xl.get("ok"):
                    xml_raw = xl.get("raw") or {}
                    lines_data = xml_raw.get("data") or []
                    # XML header'dan item'ı zenginleştir
                    xh = xml_raw.get("header") or {}
                    if xh:
                        item = dict(item)
                        item.setdefault("_xml_header", xh)
                        if xh.get("id"):
                            item["documentNumber"] = xh["id"]
                        if xh.get("issueDate"):
                            item["issueDate"] = xh["issueDate"]
            except Exception as xe:
                _logger.warning("UUID %s XML çekme hatası: %s", uuid, xe)

        vals = _map_incoming_invoice(item, self.env, client=client)
        new_inv = self.create(vals)
        _create_invoice_lines(new_inv, lines_data, self.env)
        return "created"

    # ------------------------------------------------------------------
    # Gelen Faturalar: Son N Faturayı Getir (yalnızca test entegratörü)
    # ------------------------------------------------------------------
    @api.model
    def action_fetch_last_n_incoming_from_integrator(self, n=10):
        """
        TEST AMAÇLI: tarih aralığı gözetmeksizin entegratörden en son N
        faturayı çeker (sıralama entegratör API'sinin döndürdüğü sırayla
        best-effort'tur, kesin "en yeni" garantisi yoktur). Paylaşımlı bir
        test hesabında istenen belgeyi tarih-aralıklı taramayla bulmak
        zorlaşabildiğinde hızlı bir örnekleme sağlar.

        Yalnızca is_test aktif bir entegratörde çalışır — üretimde
        tarihsiz/limitsiz sorgu istenmeyen yüke yol açabileceğinden
        kapalıdır. Zaten sistemde olan faturalar atlanır (bkz.
        _import_incoming_item).
        """
        n = int(n or 10)
        settings = self.env["ubl21.config.settings"].get_singleton()
        integrator = settings.integrator_id
        integrator_code = integrator.code if integrator else None
        if not integrator_code:
            raise UserError(_(
                "No active integrator is defined in settings.\n"
                "Fill in the IberoDoo → Settings → Integrator field."
            ))
        if not integrator.is_test:
            raise UserError(_(
                "This action can only be used on an integrator with the "
                "test environment active (Configuration → Integrators → "
                "'Test Environment Active'). Running an unbounded query on "
                "a production integrator could cause unwanted load."
            ))

        mgr = self.env["edn.document.manager"].sudo()
        client = mgr._get_integrator_client(integrator_code)

        filters = {
            "document_type": "invoice",
            "include_lines": True,
            "page_size": n,
        }
        result = self.env["edn.document.manager"].get_incoming_documents(
            integrator_code, filters, client=client
        )
        if not result.get("ok"):
            raise UserError(_(
                "Could not fetch data from integrator:\n%s"
            ) % result.get("error", "Unknown error"))

        items = result.get("documents") or []
        if not items:
            raw = result.get("raw")
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = (
                    raw.get("items") or raw.get("data") or
                    raw.get("documents") or raw.get("invoices") or
                    raw.get("results") or []
                )
        items = items[:n]

        created = skipped = errors = 0
        for item in items:
            try:
                status = self._import_incoming_item(item, client)
                if status == "created":
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                _logger.error("Son N fatura işlenirken hata: %s", str(e), exc_info=True)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Last %d Invoices from Integrator (Test)") % n,
                "message": _(
                    "%(total)d invoice(s) evaluated.\n"
                    "New: %(c)d  |  Already in system (skipped): %(s)d  |  Errors: %(e)d"
                ) % {"total": created + skipped + errors,
                     "c": created, "s": skipped, "e": errors},
                "type": "success" if not errors else "warning",
                "sticky": True,
            },
        }

    # ------------------------------------------------------------------
    # Gelen Faturalar: UUID İle Getir (liste/tarih filtresine bağımlı değil)
    # ------------------------------------------------------------------
    @api.model
    def action_fetch_by_uuid_from_integrator(self, doc_uuid):
        """
        Bilinen bir UUID (GUID) ile entegratörden doğrudan TEK bir belge
        çeker — inbox listesi/tarih filtresi hiç devreye girmez.

        Paylaşımlı bir test hesabında "alındı" bayrağı belgeyi inbox
        listesinden düşürse bile, UUID zaten biliniyorsa (ör. destek
        ekibinden veya başka bir kullanıcıdan alınmışsa) bu yöntemle yine
        çekilebilir — tabii entegratör API'si bu tür bir sorguyu bayraktan
        bağımsız işletiyorsa; bu, entegratöre/API'ye göre değişir.
        """
        doc_uuid = (doc_uuid or "").strip()
        if not doc_uuid:
            raise UserError(_("UUID cannot be empty."))

        existing = self.search([
            ("UUID", "=", doc_uuid),
            ("invoice_direction", "=", "incoming"),
        ], limit=1)
        if existing:
            raise UserError(_(
                "This document already exists in the system (Document No: %s)."
            ) % existing.id_value)

        settings = self.env["ubl21.config.settings"].get_singleton()
        integrator_code = settings.integrator_id.code if settings.integrator_id else None
        if not integrator_code:
            raise UserError(_(
                "No active integrator is defined in settings.\n"
                "Fill in the IberoDoo → Settings → Integrator field."
            ))

        mgr = self.env["edn.document.manager"].sudo()
        client = mgr._get_integrator_client(integrator_code)
        if not hasattr(client, "get_invoice_lines"):
            raise UserError(_("This integrator does not support fetching a single document by UUID."))

        xl = client.get_invoice_lines(doc_uuid)
        if not xl.get("ok"):
            raise UserError(_(
                "Could not fetch document by UUID:\n%s"
            ) % xl.get("error", "Unknown error"))

        xml_raw = xl.get("raw") or {}
        xh = xml_raw.get("header") or {}
        lines_data = xml_raw.get("data") or []

        fake_item = {
            "id": doc_uuid,
            "documentNumber": xh.get("id"),
            "issueDate": xh.get("issueDate"),
            "profileId": xh.get("profileId"),
            "invoiceTypeCode": xh.get("invoiceTypeCode"),
            "documentCurrencyCode": xh.get("currencyCode"),
            "_xml_header": xh,
        }
        vals = _map_incoming_invoice(fake_item, self.env, client=client)
        xml_clean = xml_raw.get("xml_clean") or ""
        if xml_clean:
            vals["xml_data"] = xml_clean

        new_inv = self.create(vals)
        if lines_data:
            _create_invoice_lines(new_inv, lines_data, self.env)

        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n_tr.ubl.invoice",
            "res_id": new_inv.id,
            "view_mode": "form",
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Tek Gelen Fatura: XML'den Güncelle (form butonu)
    # ------------------------------------------------------------------
    def action_fetch_single_incoming(self):
        """
        Form view butonu — sadece bu faturayı NES XML'den günceller.
        UUID yoksa hata verir; varsa XML çekip tüm alanları doldurur.
        """
        self.ensure_one()
        if not self.UUID:
            raise UserError(_("No UUID found on this invoice."))

        settings = self.env["ubl21.config.settings"].get_singleton()
        integrator_code = settings.integrator_id.code if settings.integrator_id else None
        if not integrator_code:
            raise UserError(_("No active integrator is defined in settings."))

        mgr = self.env["edn.document.manager"].sudo()
        client = mgr._get_integrator_client(integrator_code)
        xml_result = client.get_invoice_lines(self.UUID)
        if not xml_result.get("ok"):
            raise UserError(
                _("Could not fetch XML:\n%s") % xml_result.get("error", "Unknown error")
            )

        raw = xml_result.get("raw") or {}
        xml_header = raw.get("header") or {}
        lines_data = raw.get("data") or []
        totals     = raw.get("documentTotals") or {}

        fake_item = {
            "id":               self.UUID,
            "documentNumber":   xml_header.get("id") or self.id_value,
            "issueDate":        xml_header.get("issueDate"),
            "profileId":        xml_header.get("profileId"),
            "invoiceTypeCode":  xml_header.get("invoiceTypeCode"),
            "documentCurrencyCode": xml_header.get("currencyCode") or totals.get("currencyID"),
            "payableAmount":    float(totals.get("payableAmount") or 0),
            "lineExtensionAmount": float(totals.get("lineExtensionAmount") or 0),
            "taxAmount":        float(totals.get("taxAmount") or 0),
            "_xml_header":      xml_header,
        }

        vals = _map_incoming_invoice(fake_item, self.env, client=client)
        xml_clean = raw.get("xml_clean") or ""
        if xml_clean:
            vals["xml_data"] = xml_clean

        self.sudo().write(vals)

        if lines_data:
            self.line_ids.unlink()
            _create_invoice_lines(self, lines_data, self.env)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Invoice Updated"),
                "message": _("Invoice %s updated from %s.") % (self.id_value, integrator_code),
                "type": "success",
                "sticky": False,
                # Satırlar unlink+create ile yenilendiğinden formu da yeniden yükle;
                # aksi halde ekranda silinen eski satır id'leri kalır ve sonraki
                # işlemde "kayıt bulunamadı" hatası verir.
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "l10n_tr.ubl.invoice",
                    "res_id": self.id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "target": "current",
                },
            },
        }

    # ------------------------------------------------------------------
    # Giden Faturalar: Güncelle (write_date korumalı)
    # ------------------------------------------------------------------
    @api.model
    def action_sync_outgoing_from_erp(self):
        """
        Odoo'dan giden faturaları çeker.
        - draft: her zaman güncellenir
        - sent/approved + write_date > erp_last_sync_date: atlanır
        """
        settings = self.env["ubl21.config.settings"].get_singleton()
        if not settings:
            raise UserError("Settings not found.")

        if settings.active_erp == "sap_b1":
            return self.action_sync_from_erp()

        return self._sync_outgoing_odoo_native(settings)

    def _sync_outgoing_odoo_native(self, settings):
        from ..erp.odoo_native_connector import OdooNativeConnector
        from ..erp.odoo_native_mapper import OdooERPMapper

        connector = OdooNativeConnector(self.env)
        mapper = OdooERPMapper(self.env)
        last_sync = settings.last_invoice_sync_datetime
        sync_start = fields.Datetime.now()
        created = updated = skipped = errors = 0

        moves = connector.fetch_invoices(last_sync_datetime=last_sync)

        for move in moves:
            try:
                move_id_str = str(move.id)
                existing = self.search([
                    ("erp_id", "=", move_id_str),
                    ("erp_object_type", "=", mapper.get_invoice_object_type()),
                    ("invoice_direction", "=", "outgoing"),
                ], limit=1)

                header_vals = mapper.map_invoice_header(move)
                header_vals["erp_last_sync_date"] = fields.Datetime.now()

                if existing:
                    is_draft = existing.gib_status == "draft"
                    manually_edited = (
                        existing.erp_last_sync_date and existing.write_date
                        and existing.write_date > existing.erp_last_sync_date
                    )
                    if not is_draft and manually_edited:
                        _logger.info(
                            "Fatura %s atlandı — gönderilmiş + manuel değişiklik",
                            existing.id_value,
                        )
                        skipped += 1
                        continue
                    existing.write(header_vals)
                    self._sync_invoice_lines_from_odoo(existing, move, mapper)
                    updated += 1
                else:
                    new_inv = self.create(header_vals)
                    self._sync_invoice_lines_from_odoo(new_inv, move, mapper)
                    created += 1

            except Exception as e:
                errors += 1
                _logger.error("Giden fatura %s işlenirken hata: %s", move.name, str(e))

        settings.write({"last_invoice_sync_datetime": sync_start})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Invoices Updated"),
                "message": _(
                    "Created: %(c)d  |  Updated: %(u)d  |  "
                    "Skipped: %(s)d  |  Errors: %(e)d"
                ) % {"c": created, "u": updated, "s": skipped, "e": errors},
                "type": "success" if not errors else "warning",
                "sticky": bool(errors),
            },
        }

    # ------------------------------------------------------------------
    # Entegratör durum sorgulama (genel — tüm provider'lar için)
    # ------------------------------------------------------------------

    def _get_integrator_code(self):
        settings = self.env["ubl21.config.settings"].get_singleton()
        return settings.integrator_id.code if settings and settings.integrator_id else None

    def _fetch_and_store_pdf_from_integrator(self, integrator_code):
        """Entegratörden PDF indirir ve pdf_data alanına kaydeder. Hata olursa False döner."""
        self.ensure_one()
        if not self.UUID or not integrator_code:
            return False
        mgr = self.env["edn.document.manager"].sudo()
        if self.invoice_direction == "incoming":
            result = mgr.get_incoming_document_pdf(integrator_code, self.UUID, doc_type="invoice")
        else:
            result = mgr.get_outgoing_document_pdf(integrator_code, self.UUID, doc_type="invoice")
        if result.get("ok") and result.get("pdf_bytes"):
            self.pdf_data = base64.b64encode(result["pdf_bytes"])
            return True
        return False

    def action_preview_pdf(self):
        """
        PDF önizleme: önce entegratörden dener (gelen faturalarda veya
        gönderilmiş/onaylanmış/reddedilmiş giden faturalarda), başarısız
        olursa iber_e_transform'un standart (XSLT tabanlı) önizlemesine
        geri döner.

        NOT: Bu metod önceden yalnızca iber_edonusum_nes'te tanımlıydı;
        mantığı tamamen provider-agnostik (yalnızca _get_integrator_code /
        _fetch_and_store_pdf_from_integrator kullanıyor) olduğundan buraya,
        tüm entegratörlerin (Hızlı, NES, Uyumsoft) ortak yararlanacağı
        şekilde taşındı. Gelen faturalarda (özellikle Uyumsoft gibi
        entegratörlerde) UUID standart XSLT akışı için anlamlı değildir —
        o akış yalnızca giden fatura üretimi için tasarlanmıştır ve gelen
        faturalarda çağrılırsa hata verir.
        """
        self.ensure_one()
        integrator_code = self._get_integrator_code()
        use_integrator = (
            integrator_code and self.UUID and (
                self.invoice_direction == "incoming" or
                self.gib_status in ("sent", "approved", "rejected")
            )
        )
        integrator_warning = None
        if use_integrator:
            try:
                ok = self._fetch_and_store_pdf_from_integrator(integrator_code)
                if not ok:
                    integrator_warning = _("Could not fetch PDF from the integrator, using standard preview.")
                    use_integrator = False
            except Exception as e:
                integrator_warning = _("Integrator PDF error: %s\nUsing standard preview.") % str(e)
                use_integrator = False

        if not use_integrator:
            try:
                self.pdf_data = self.get_pdf_data()
            except Exception as e:
                raise UserError(_("Could not generate PDF:\n%s") % str(e))

        filename_base = (self.id_value or "document").strip("/").replace("/", "-") or "document"
        wizard = self.env["l10n_tr.ubl.invoice.pdf.preview.wizard"].create({
            "pdf_data": self.pdf_data,
            "pdf_filename": f"{filename_base}.pdf",
            "xml_data": self.xml_data,
            "xml_filename": f"{filename_base}.xml",
        })
        action = {
            "type": "ir.actions.act_window",
            "name": _("PDF Preview"),
            "res_model": "l10n_tr.ubl.invoice.pdf.preview.wizard",
            "view_mode": "form",
            "views": [(self.env.ref("iber_e_transform.view_ubl_invoice_pdf_preview_wizard_form").id, "form")],
            "res_id": wizard.id,
            "target": "new",
        }

        if integrator_warning:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("PDF Warning"),
                    "message": integrator_warning,
                    "type": "warning",
                    "sticky": False,
                    "next": action,
                },
            }
        return action

    def action_fetch_outgoing_status(self):
        """Entegratörden giden faturanın güncel durumunu çeker ve GIB alanlarını günceller."""
        self.ensure_one()

        if not self.UUID:
            raise UserError("No UUID found on this invoice. Send it to GIB first.")
        if self.invoice_direction != "outgoing":
            raise UserError("This action is only valid for outgoing invoices.")

        integrator_code = self._get_integrator_code()
        if not integrator_code:
            raise UserError(
                "No active integrator is defined in settings. "
                "Please fill in the IberoDoo → Settings → Integrator field."
            )

        mgr = self.env["edn.document.manager"]
        result = mgr.get_outgoing_invoice_status(integrator_code, self.UUID)

        if not result.get("ok"):
            raise UserError(
                f"Could not fetch status from integrator:\n{result.get('error', 'Unknown error')}"
            )

        client = mgr._get_integrator_client(integrator_code)
        raw_status = (result.get("status") or "").upper()
        new_gib_status = client.translate_status(raw_status) if raw_status else None

        vals = {}
        if new_gib_status and new_gib_status != self.gib_status:
            vals["gib_status"] = new_gib_status

        envelope_id = result.get("envelope_id")
        if envelope_id:
            vals["gib_envelope_id"] = envelope_id

        response_date = result.get("response_date")
        if response_date:
            vals["gib_response_date"] = response_date

        response_note = result.get("response_note")
        if response_note:
            vals["gib_response_desc"] = response_note

        invoice_number = result.get("invoice_number")
        if invoice_number and invoice_number != self.id_value:
            vals["id_value"] = invoice_number

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{ts}] Durum sorgulandı → {integrator_code}: {raw_status or '?'}"
        if response_note:
            log_line += f" | Not: {response_note}"
        vals["gib_log"] = ((self.gib_log or "") + "\n" + log_line).strip()

        self.write(vals)
        self._on_outgoing_status_fetched(result, client)

        try:
            self._fetch_and_store_pdf_from_integrator(integrator_code)
        except Exception:
            pass

        status_label = {
            "approved": "Onaylandı",
            "rejected": "Reddedildi",
            "sent": "Gönderildi / Bekliyor",
            "error": "Hata",
        }.get(new_gib_status or self.gib_status, raw_status or "Bilinmiyor")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Entegratör Durumu Güncellendi",
                "message": f"Fatura Durumu: {status_label}"
                + (f"\nSeri No: {invoice_number}" if invoice_number else "")
                + (f"\nZarf: {envelope_id}" if envelope_id else ""),
                "type": "success" if new_gib_status == "approved" else (
                    "danger" if new_gib_status in ("rejected", "error") else "info"
                ),
                "sticky": new_gib_status in ("rejected", "error"),
            },
        }

    def _on_outgoing_status_fetched(self, result, client):
        """Extension hook — provider addon'ları NES/Uyumsoft gibi özgün alanlar için override eder."""
        pass
