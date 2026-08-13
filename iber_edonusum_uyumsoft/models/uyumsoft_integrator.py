# -*- coding: utf-8 -*-
"""
Uyumsoft e-Fatura Entegratörü — SOAP (WCF "Integration" servisi)
==================================================================

2026-08-07'de firmanın bildirdiği gerçek test adresi üzerinden WSDL
(``https://efaturaws-test.uyum.com.tr/Services/Integration?singleWsdl``)
indirilip incelenerek doğrulanan bilgiler:

  - Tek endpoint, SOAP 1.1 (BasicHttpBinding): .../Services/Integration
  - Namespace: gövde elemanları ``http://tempuri.org/`` (tns); UBL fatura
    gövdesi ``urn:oasis:names:specification:ubl:schema:xsd:Invoice-2``.
  - Auth: WS-Security UsernameToken (PasswordText), transport (HTTPS)
    düzeyinde — mesaj imzalama YOK, istekte wsu:Timestamp GÖNDERİLMEZ
    (yalnızca yanıtta sunucu ekler — bkz. ``_security_header`` NOT'u).
    Password Type URI'si standart OASIS adresidir:
    ``.../oasis-200401-wss-username-token-profile-1.0#PasswordText``
    ("wssecurity-username-token-profile" DEĞİL — bu yanlış varyant firma
    sunucusunda "a:InvalidSecurity" Fault'una sebep oluyordu, 2026-08-10'da
    firmanın paylaştığı gerçek çalışan örnekle (WhoAmIRequest.xml) teyit
    edilip düzeltildi).
  - Her operation ``<Op>Result`` adlı bir yanıt tipi döner; ortak alanlar:
    ``IsSucceded`` (bool, NOT: "Succeded" — firma API'sindeki yazım hatası
    aynen korunmuştur) ve ``Message`` (str).
  - Gerçek durum enum'u (``InvoiceStatus``): NotPrepared, NotSend, Draft,
    Canceled, Queued, Processing, SentToGib, Approved, WaitingForAprovement,
    Declined, Return, EArchivedCanceled, Error.

Bu istemci, codebase'deki diğer bağlayıcılarla (Hızlı, NES, N11) aynı
konvansiyonu izler: harici SOAP kütüphanesi (zeep vb.) KULLANMAZ, ham
``requests`` + ``xml.etree.ElementTree`` ile zarf oluşturur/ayrıştırır
(bkz. iber_marketplace_n11/core/n11_client.py).

DOĞRULANDI (2026-08-10): Test kullanıcı adı/şifresi (Uyumsoft/Uyumsoft) ile
gerçek bir ``WhoAmI`` çağrısı ``curl`` ve Odoo üzerinden başarıyla test
edildi — HTTP 200, ``IsSucceded="true"``, gerçek müşteri verisi döndü.

DOĞRULANMAMIŞ NOKTALAR — canlı hesapla teyit edilmeden production'a
alınmamalı:
  - Üretim (prod) URL'i tahminen "https://efaturaws.uyum.com.tr" (test
    alan adındaki "-test" kaldırılarak) — firmayla teyit edilmeli.
  - ``send_document``'ta UBL ``<Invoice>`` gövdesinin ``InvoiceInfo`` içine
    yerleştirilme şekli şemadan (``Invoice`` alanı ``q2:InvoiceType``)
    çıkarılmıştır ama canlı bir başarılı çağrı ile TEYİT EDİLMEMİŞTİR.
  - ``get_incoming_documents``'taki ``InboxInvoiceListQueryModel`` gövdesi
    WSDL şemasındaki alan sırasına göre inşa edilmiştir (WCF DataContract
    sırayı önemser); nil/varsayılan değerlerin sunucu tarafından kabul
    edilip edilmediği canlı çağrı ile doğrulanmamıştır.
"""
import logging
import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import requests

from odoo.addons.iber_edonusum.models.integrator_base import IntegratorBase

_logger = logging.getLogger(__name__)

_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
_TNS = "http://tempuri.org/"
_WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
_WSU_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

_ACTION_IINTEGRATION = "http://tempuri.org/IIntegration"

_UBL_NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


def _xml_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _strip_ns(tag: str) -> str:
    return re.sub(r"\{[^}]+\}", "", tag)


def _elem_to_dict(elem) -> dict:
    """SOAP yanıt elemanını dict'e çevirir (attribute'lar dahil)."""
    result = {}
    for akey, aval in elem.attrib.items():
        result[_strip_ns(akey)] = aval
    children = list(elem)
    if not children:
        text = (elem.text or "").strip()
        if text and not result:
            return text
        if text:
            result["_text"] = text
        return result
    for child in children:
        key = _strip_ns(child.tag)
        val = _elem_to_dict(child)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(val)
        else:
            result[key] = val
    return result


def _xt(el, path, ns=_UBL_NS, default=""):
    if el is None:
        return default
    found = el.find(path, ns)
    return (found.text or "").strip() if found is not None else default


def _party_tax_number(party_el, ns=_UBL_NS):
    """VKN/TCKN'yi önce cac:PartyTaxScheme/cbc:CompanyID'den, orada yoksa
    cac:PartyIdentification[schemeID=VKN|TCKN]/cbc:ID'den okur.

    GİB UBL-TR XML'lerinde ikisi de kullanılabiliyor — canlı bir örnekte
    (PNR2026000000115, 2026-08-13'te tespit edildi) PartyTaxScheme yalnızca
    TaxScheme/Name (vergi dairesi) taşıyordu, VKN yalnızca
    PartyIdentification'da vardı; yalnızca CompanyID'ye bakan eski kod bu
    durumda VKN'yi boş bırakıyordu.
    """
    if party_el is None:
        return ""
    val = _xt(party_el, "cac:PartyTaxScheme/cbc:CompanyID", ns)
    if val:
        return val
    for scheme in ("VKN", "TCKN"):
        val = _xt(party_el, f"cac:PartyIdentification/cbc:ID[@schemeID='{scheme}']", ns)
        if val:
            return val
    return ""


def _parse_ubl_xml(xml_text: str) -> dict:
    """UBL-TR XML'ini get_invoice_lines'ın beklediği formata çevirir (Hızlı/NES ile aynı sözleşme)."""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    header = {
        "id": _xt(root, "cbc:ID"),
        "issueDate": _xt(root, "cbc:IssueDate"),
        "profileId": _xt(root, "cbc:ProfileID"),
        "invoiceTypeCode": _xt(root, "cbc:InvoiceTypeCode"),
        "currencyCode": _xt(root, "cbc:DocumentCurrencyCode"),
    }
    sup = root.find("cac:AccountingSupplierParty/cac:Party", _UBL_NS)
    if sup is not None:
        header["supplier"] = {
            "name": _xt(sup, "cac:PartyName/cbc:Name") or _xt(sup, "cac:Person/cbc:FirstName"),
            "taxNumber": _party_tax_number(sup),
            "taxOfficeName": _xt(sup, "cac:PartyTaxScheme/cac:TaxScheme/cbc:Name"),
            "streetName": _xt(sup, "cac:PostalAddress/cbc:StreetName"),
            "cityName": _xt(sup, "cac:PostalAddress/cbc:CityName"),
            "district": _xt(sup, "cac:PostalAddress/cbc:CitySubdivisionName"),
            "postalZone": _xt(sup, "cac:PostalAddress/cbc:PostalZone"),
            "countryCode": _xt(sup, "cac:PostalAddress/cac:Country/cbc:IdentificationCode", default="TR"),
        }
    cus = root.find("cac:AccountingCustomerParty/cac:Party", _UBL_NS)
    if cus is not None:
        header["customer"] = {
            "name": _xt(cus, "cac:PartyName/cbc:Name") or _xt(cus, "cac:Person/cbc:FirstName"),
            "taxNumber": _party_tax_number(cus),
        }
    totals = {
        "payableAmount": _xt(root, "cac:LegalMonetaryTotal/cbc:PayableAmount"),
        "lineExtensionAmount": _xt(root, "cac:LegalMonetaryTotal/cbc:LineExtensionAmount"),
        "taxAmount": _xt(root, "cac:TaxTotal/cbc:TaxAmount"),
        "currencyID": header.get("currencyCode", "TRY"),
    }
    lines = []
    for line_el in root.findall("cac:InvoiceLine", _UBL_NS):
        qty_el = line_el.find("cbc:InvoicedQuantity", _UBL_NS)
        discounts = []
        for ac in line_el.findall("cac:AllowanceCharge", _UBL_NS):
            charge_indicator = (_xt(ac, "cbc:ChargeIndicator", default="false")).strip().lower() == "true"
            discounts.append({
                "type": "surcharge" if charge_indicator else "discount",
                "rate": _xt(ac, "cbc:MultiplierFactorNumeric"),
                "amount": _xt(ac, "cbc:Amount"),
                "baseAmount": _xt(ac, "cbc:BaseAmount"),
                "description": _xt(ac, "cbc:AllowanceChargeReason"),
            })
        line_data = {
            "lineId": _xt(line_el, "cbc:ID"),
            "quantity": _xt(line_el, "cbc:InvoicedQuantity"),
            "unitCode": (qty_el.get("unitCode") if qty_el is not None else None) or "C62",
            "lineExtensionAmount": _xt(line_el, "cbc:LineExtensionAmount"),
            "name": _xt(line_el, "cac:Item/cbc:Name"),
            "priceAmount": _xt(line_el, "cac:Price/cbc:PriceAmount"),
            "percent": "0",
            "taxAmount": "0",
            "taxableAmount": "0",
            "taxSchemeName": "KDV",
            "description": _xt(line_el, "cac:Item/cbc:Description"),
            "sellersItemIdentification": _xt(line_el, "cac:Item/cac:SellersItemIdentification/cbc:ID"),
            "discounts": discounts,
        }
        # Tüm TaxTotal/TaxSubtotal'ları gez: KDV (0015) ana alanlara,
        # diğerleri (ÖTV vb.) taxExtras listesine yazılır (bkz. Hızlı entegratörü,
        # aynı mantık — 2026-08-13'te tevkifatlı bir belgede bu blok eksik olduğu
        # için satır tevkifat verisi kayboluyordu).
        tax_extras = []
        for tax_total in line_el.findall("cac:TaxTotal", _UBL_NS):
            for tax_sub in tax_total.findall("cac:TaxSubtotal", _UBL_NS):
                scheme = tax_sub.find("cac:TaxCategory/cac:TaxScheme", _UBL_NS)
                scheme_code = (_xt(scheme, "cbc:TaxTypeCode") if scheme is not None else "") or \
                              (_xt(scheme, "cbc:ID") if scheme is not None else "") or "0015"
                scheme_name = (_xt(scheme, "cbc:Name") if scheme is not None else "") or ""
                taxable_amount = _xt(tax_sub, "cbc:TaxableAmount") or "0"
                tax_amount = _xt(tax_sub, "cbc:TaxAmount") or "0"
                percent = _xt(tax_sub, "cbc:Percent") or "0"

                if scheme_code == "0015":
                    line_data["taxableAmount"] = taxable_amount
                    line_data["taxAmount"] = tax_amount
                    line_data["percent"] = percent
                    line_data["taxSchemeName"] = scheme_name or "KDV"
                else:
                    tax_extras.append({
                        "code": scheme_code,
                        "name": scheme_name,
                        "rate": percent,
                        "taxableAmount": taxable_amount,
                        "amount": tax_amount,
                    })
        if tax_extras:
            line_data["taxExtras"] = tax_extras

        # Tevkifat (cac:WithholdingTaxTotal)
        wh_total = line_el.find("cac:WithholdingTaxTotal", _UBL_NS)
        if wh_total is not None:
            wh_sub = wh_total.find("cac:TaxSubtotal", _UBL_NS)
            if wh_sub is not None:
                wh_scheme = wh_sub.find("cac:TaxCategory/cac:TaxScheme", _UBL_NS)
                wh_code = (_xt(wh_scheme, "cbc:TaxTypeCode") if wh_scheme is not None else "") or \
                          (_xt(wh_scheme, "cbc:ID") if wh_scheme is not None else "") or ""
                line_data["withholdingRate"] = _xt(wh_sub, "cbc:Percent") or "0"
                line_data["withholdingCode"] = wh_code

        lines.append(line_data)
    return {"header": header, "data": lines, "documentTotals": totals, "xml_clean": xml_text}


class UyumsoftIntegrator(IntegratorBase):
    code = "UYUMSOFT"
    name = "Uyumsoft"

    # WSDL InvoiceStatus enum → gib_status
    status_map = {
        "APPROVED": "approved",
        "SENTTOGIB": "sent",
        "QUEUED": "sent",
        "PROCESSING": "sent",
        "WAITINGFORAPROVEMENT": "sent",
        "DRAFT": "sent",
        "DECLINED": "rejected",
        "RETURN": "rejected",
        "CANCELED": "rejected",
        "EARCHIVEDCANCELED": "rejected",
        "ERROR": "error",
        "NOTSEND": "error",
        "NOTPREPARED": "error",
    }

    answer_map = {
        "none": "none",
        "waiting": "waiting",
        "accepted": "accepted",
        "rejected": "rejected",
    }

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._timeout = int(self.settings.get("timeout", 30))

    # ------------------------------------------------------------------
    # SOAP altyapısı
    # ------------------------------------------------------------------

    def _base_url(self, settings=None) -> str:
        s = settings or self.settings
        return (s.get("url") or "").rstrip("/")

    def _endpoint(self, settings=None) -> str:
        return f"{self._base_url(settings)}/Services/Integration"

    def _security_header(self, settings=None) -> str:
        """
        NOT: Bu format Uyumsoft'un 2026-08-10'da paylaştığı gerçek çalışan
        örnek (WhoAmIRequest.xml) ile birebir teyit edilmiştir:
          - İstekte wsu:Timestamp GÖNDERİLMEZ (yalnızca yanıtta sunucu ekler).
          - Password Type URI'si standart OASIS UsernameToken Profile 1.0
            adresidir: ".../oasis-200401-wss-username-token-profile-1.0#PasswordText"
            (İlk yazımda yanlışlıkla "wss-wssecurity-username-token-profile-1.0"
            kullanılmıştı — bu, sunucunun her istekte "a:InvalidSecurity" SOAP
            Fault döndürmesine sebep oluyordu; kanıt: aynı istek düzeltilmiş
            URI ile HTTP 200 + IsSucceded="true" döndü.)
        """
        s = settings or self.settings
        username = s.get("username") or ""
        password = s.get("password") or ""
        return (
            f'<wsse:Security soapenv:mustUnderstand="1" xmlns:wsse="{_WSSE_NS}" xmlns:wsu="{_WSU_NS}">'
            f"<wsse:UsernameToken>"
            f"<wsse:Username>{_xml_escape(username)}</wsse:Username>"
            f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">'
            f"{_xml_escape(password)}</wsse:Password>"
            f"</wsse:UsernameToken>"
            f"</wsse:Security>"
        )

    def _envelope(self, body_xml: str, settings=None) -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}" xmlns:tns="{_TNS}" xmlns:i="{_XSI_NS}">'
            f"<soapenv:Header>{self._security_header(settings)}</soapenv:Header>"
            f"<soapenv:Body>{body_xml}</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    def _call(self, operation: str, body_xml: str, settings=None) -> dict:
        """SOAP zarfı oluşturur, POST eder, Fault/Result'u ayrıştırır."""
        settings = settings or self.settings
        envelope = self._envelope(body_xml, settings)
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{_ACTION_IINTEGRATION}/{operation}"',
        }
        try:
            resp = requests.post(
                self._endpoint(settings),
                data=envelope.encode("utf-8"),
                headers=headers,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            return {"ok": False, "error": f"HTTP bağlantı hatası: {exc}"}

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            return {"ok": False, "error": f"SOAP yanıt ayrıştırma hatası — HTTP {resp.status_code}: {exc}"}

        fault = root.find(f".//{{{_SOAP_NS}}}Fault")
        if fault is not None:
            code_el = fault.find("faultcode")
            str_el = fault.find("faultstring")
            code = code_el.text if code_el is not None else ""
            msg = str_el.text if str_el is not None else resp.text
            return {"ok": False, "error": f"SOAP Fault [{code}]: {msg}"}

        if not resp.ok:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:500]}"}

        body = root.find(f".//{{{_SOAP_NS}}}Body")
        if body is None or not list(body):
            return {"ok": False, "error": "Boş SOAP yanıtı"}
        response_wrapper = list(body)[0]  # <{Operation}Response>
        result_children = list(response_wrapper)
        if not result_children:
            return {"ok": True, "raw": {}}
        result_el = result_children[0]  # <{Operation}Result>
        result = _elem_to_dict(result_el)

        is_ok = str(result.get("IsSucceded", "true")).strip().lower() == "true"
        if not is_ok:
            return {"ok": False, "raw": result, "error": result.get("Message") or "Uyumsoft hatası"}
        return {"ok": True, "raw": result}

    # ------------------------------------------------------------------
    # IntegratorBase implementasyonları
    # ------------------------------------------------------------------

    def get_token(self, settings: dict = None) -> dict:
        """
        WS-Security kimlik bilgisi her istekte gönderildiği için ayrı bir
        login/token adımı yok; ``WhoAmI`` çağrısıyla kimlik doğrulanır.

        NOT: ``edn.document.manager._get_integrator_client`` bu metodu
        ``client.get_token(settings)`` şeklinde çağırır (bkz. iber_edonusum/
        models/document_manager.py) — IntegratorBase'in soyut imzasından
        (parametresiz) farklı olarak ``settings`` alınır; Hızlı entegratörüyle
        aynı, gerçekte çağrılan imza izlenir.
        """
        settings = settings or self.settings
        if not (self._base_url(settings) and settings.get("username") and settings.get("password")):
            return {"ok": False, "token": None, "raw": None, "error": "URL/kullanıcı adı/şifre eksik."}
        result = self._call("WhoAmI", "<tns:WhoAmI/>", settings=settings)
        if not result.get("ok"):
            return {"ok": False, "token": None, "raw": result.get("raw"), "error": result.get("error")}
        return {"ok": True, "token": "stateless", "raw": result.get("raw"), "error": None}

    def send_document(self, document: dict) -> dict:
        """
        SendInvoice — zaten üretilmiş UBL-TR XML'i (``document_data["File"]``,
        iber_e_transform/iber_service_layer çıktısı) ``InvoiceInfo.Invoice``
        alanına gömer.

        NOT: Bu yerleşim canlı bir başarılı çağrı ile TEYİT EDİLMEMİŞTİR —
        modül docstring'ine bakın.
        """
        xml_content = (document.get("File") or "").strip()
        xml_content = re.sub(r"^<\?xml[^>]*\?>\s*", "", xml_content)  # nested prolog olamaz
        if not xml_content:
            return {"ok": False, "error": "Gönderilecek UBL XML içeriği boş."}

        profile = (document.get("DocumentProfile") or "").upper()
        scenario = "eArchive" if profile == "EARSIVFATURA" else "eInvoice"
        create_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        body = (
            "<tns:SendInvoice><tns:invoices>"
            "<tns:InvoiceInfo>"
            f"<tns:Invoice>{xml_content}</tns:Invoice>"
            f"<tns:Scenario>{scenario}</tns:Scenario>"
            f"<tns:CreateDateUtc>{create_date}</tns:CreateDateUtc>"
            "</tns:InvoiceInfo>"
            "</tns:invoices></tns:SendInvoice>"
        )
        result = self._call("SendInvoice", body)
        if not result.get("ok"):
            return result
        return {"ok": True, "uuid": document.get("UUID"), "raw": result.get("raw"), "error": None}

    def get_incoming_documents(self, filters: dict | None = None) -> dict:
        """
        GetInboxInvoiceList — gelen fatura listesini getirir.

        ``query`` gövdesi WSDL'deki ``InboxInvoiceListQueryModel`` şemasının
        alan sırasına göre inşa edilmiştir (WCF DataContract sıraya
        duyarlıdır). Filtrelenmeyen nillable alanlar ``i:nil="true"`` ile
        boş geçilir.
        """
        filters = filters or {}
        start = filters.get("startDate") or filters.get("startCreateDate") or ""
        end = filters.get("endDate") or filters.get("endCreateDate") or ""

        def _iso_start(d):
            if not d:
                return None
            return f"{d[:10]}T00:00:00Z"

        def _iso_end(d):
            """Bitiş tarihini gün SONU olarak ayarlar — aksi halde o günün
            (özellikle bugünün) gece yarısından sonra oluşturulan faturalar
            filtre dışında kalır (2026-08-10'da PNR2026000000080 ile canlı
            olarak teyit edilen bug: CreateEndDate=T00:00:00Z, fatura
            CreateDateUtc=09:17'de oluşmuştu, filtre onu dışarıda bırakıyordu)."""
            if not d:
                return None
            return f"{d[:10]}T23:59:59Z"

        def _el(tag, value):
            if value is None:
                return f'<tns:{tag} i:nil="true"/>'
            return f"<tns:{tag}>{_xml_escape(str(value))}</tns:{tag}>"

        create_start = _iso_start(start)
        create_end = _iso_end(end)
        page_size = int(filters.get("page_size") or 100)

        query_body = (
            '<tns:query '
            # NOT: OnlyNewestInvoices="true" bu test kiracısında (tenant)
            # tüm sonuçları eledi (2026-08-10'da curl ile TotalCount=0 vs
            # false ile TotalCount=183 olarak doğrulandı) — muhtemelen bu
            # alanın gerçek anlamı (en güncel versiyon) demo veride düzgün
            # işaretlenmemiş. Bu yüzden varsayılan olarak false kullanılıyor.
            f'PageIndex="0" PageSize="{page_size}" OnlyNewestInvoices="false">'
            + _el("ExecutionStartDate", None)
            + _el("ExecutionEndDate", None)
            + _el("CreateStartDate", create_start)
            + _el("CreateEndDate", create_end)
            + _el("Status", None)
            + _el("SortColumn", None)
            + _el("SortMode", None)
            + _el("IsArchived", None)
            + "<tns:IncludeTagList>false</tns:IncludeTagList>"
            + "</tns:query>"
        )
        body = f"<tns:GetInboxInvoiceList>{query_body}</tns:GetInboxInvoiceList>"

        result = self._call("GetInboxInvoiceList", body)
        if not result.get("ok"):
            return result

        raw = result.get("raw") or {}
        value = raw.get("Value") or {}
        items = value.get("Items") or []
        if isinstance(items, dict):
            items = [items]

        documents = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # NOT (2026-08-10 canlı testle doğrulandı): GetInboxInvoiceData/
            # GetInboxInvoicePdf gibi teknik sorgulamalar "DocumentId" (GUID)
            # bekliyor — "InvoiceId" (iş/fatura numarası, örn. PNR2026...) ile
            # çağrıldığında "İlgili fatura bulunamadı" hatası dönüyor. Bu
            # yüzden uuid=DocumentId, documentNumber(Belge No)=InvoiceId.
            document_guid = item.get("DocumentId") or ""
            documents.append({
                "id": document_guid,
                "uuid": document_guid,
                "documentNumber": item.get("InvoiceId") or "",
                "issueDate": item.get("CreateDateUtc") or "",
                "senderIdentifier": item.get("TargetTcknVkn") or "",
                "senderTitle": item.get("TargetTitle") or "",
                "receiverIdentifier": "",
                "receiverTitle": "",
                "documentStatus": item.get("Status") or "",
                "documentAnswer": "",
                "profileId": "",
                "raw": item,
            })
        return {"ok": True, "documents": documents, "raw": raw}

    def check_document_status(self, uuid: str) -> dict:
        """QueryInboxInvoiceStatus — tek/çoklu UUID ile durum sorgular."""
        body = (
            "<tns:QueryInboxInvoiceStatus><tns:invoiceIds>"
            f"<tns:string>{_xml_escape(uuid)}</tns:string>"
            "</tns:invoiceIds></tns:QueryInboxInvoiceStatus>"
        )
        result = self._call("QueryInboxInvoiceStatus", body)
        if not result.get("ok"):
            return result
        raw = result.get("raw") or {}
        value = raw.get("Value") or {}
        if isinstance(value, list):
            value = value[0] if value else {}
        return {"ok": True, "status": value.get("Status") or "", "raw": value, "error": None}

    # ------------------------------------------------------------------
    # Opsiyonel metodlar
    # ------------------------------------------------------------------

    def get_invoice_lines(self, uuid: str) -> dict:
        """GetInboxInvoiceData — XML çekip UBL-TR satırlarını parse eder."""
        body = f"<tns:GetInboxInvoiceData><tns:invoiceId>{_xml_escape(uuid)}</tns:invoiceId></tns:GetInboxInvoiceData>"
        result = self._call("GetInboxInvoiceData", body)
        if not result.get("ok"):
            return result
        raw = result.get("raw") or {}
        value = raw.get("Value") or {}
        b64 = value.get("Data") or ""
        if not b64:
            return {"ok": False, "error": "XML içeriği yanıtta bulunamadı."}
        try:
            import base64 as _b64mod
            xml_text = _b64mod.b64decode(b64).decode("utf-8", errors="replace")
        except Exception as ex:
            return {"ok": False, "error": f"Base64 decode hatası: {ex}"}
        try:
            return {"ok": True, "raw": _parse_ubl_xml(xml_text)}
        except Exception as ex:
            return {"ok": False, "error": f"XML parse hatası: {ex}"}

    def get_incoming_document_pdf(self, uuid: str, doc_type: str = "invoice") -> dict:
        """GetInboxInvoicePdf."""
        body = f"<tns:GetInboxInvoicePdf><tns:invoiceId>{_xml_escape(uuid)}</tns:invoiceId></tns:GetInboxInvoicePdf>"
        result = self._call("GetInboxInvoicePdf", body)
        if not result.get("ok"):
            return {"ok": False, "pdf_bytes": None, "error": result.get("error")}
        raw = result.get("raw") or {}
        value = raw.get("Value") or {}
        b64 = value.get("Data") or ""
        if not b64:
            return {"ok": False, "pdf_bytes": None, "error": "PDF içeriği yanıtta bulunamadı."}
        try:
            import base64 as _b64mod
            return {"ok": True, "pdf_bytes": _b64mod.b64decode(b64), "error": None}
        except Exception as ex:
            return {"ok": False, "pdf_bytes": None, "error": f"Base64 decode hatası: {ex}"}

    def get_outgoing_document_pdf(self, uuid: str, doc_type: str = "invoice") -> dict:
        """WSDL'de giden belge için ayrı bir GetOutboxInvoicePdf var; aynı imzayı kullanır."""
        body = f"<tns:GetOutboxInvoicePdf><tns:invoiceId>{_xml_escape(uuid)}</tns:invoiceId></tns:GetOutboxInvoicePdf>"
        result = self._call("GetOutboxInvoicePdf", body)
        if not result.get("ok"):
            return {"ok": False, "pdf_bytes": None, "error": result.get("error")}
        raw = result.get("raw") or {}
        value = raw.get("Value") or {}
        b64 = value.get("Data") or ""
        if not b64:
            return {"ok": False, "pdf_bytes": None, "error": "PDF içeriği yanıtta bulunamadı."}
        try:
            import base64 as _b64mod
            return {"ok": True, "pdf_bytes": _b64mod.b64decode(b64), "error": None}
        except Exception as ex:
            return {"ok": False, "pdf_bytes": None, "error": f"Base64 decode hatası: {ex}"}

    def get_outgoing_document(self, uuid: str, doc_type: str = "invoice") -> dict:
        """QueryOutboxInvoiceStatus ile giden belge durumu."""
        body = (
            "<tns:QueryOutboxInvoiceStatus><tns:invoiceIds>"
            f"<tns:string>{_xml_escape(uuid)}</tns:string>"
            "</tns:invoiceIds></tns:QueryOutboxInvoiceStatus>"
        )
        result = self._call("QueryOutboxInvoiceStatus", body)
        if not result.get("ok"):
            return result
        raw = result.get("raw") or {}
        value = raw.get("Value") or {}
        if isinstance(value, list):
            value = value[0] if value else {}
        return {
            "ok": True,
            "status": value.get("Status") or "",
            "raw": value,
            "error": None,
            "envelope_id": "",
            "invoice_number": value.get("InvoiceId") or "",
            "response_date": "",
            "response_note": value.get("Message") or "",
        }
