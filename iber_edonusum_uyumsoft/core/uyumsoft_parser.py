# -*- coding: utf-8 -*-
"""
Uyumsoft e-Fatura — UBL-TR XML parse mantığı (saf Python, Odoo bağımsız).

models/uyumsoft_integrator.py'nin SOAP zarf/istemci katmanından ayrıştırılmıştır
— yalnızca ham XML metnini iber_edonusum'un beklediği sözleşme formatına
({"header":..., "data":..., "documentTotals":..., "xml_clean":...}) çeviren
fonksiyonlar burada yer alır (bkz. sapb1_control_center/core paterni,
Cython ile derlenebilir).
"""
import re
from xml.etree import ElementTree as ET

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


def _elem_to_dict(elem):
    """SOAP yanıt elemanını dict'e çevirir (attribute'lar dahil).

    NOT: dönüş tipi kasıtlı olarak dict|str karışıktır — attribute'suz,
    alt elemanı olmayan "yaprak" XML düğümleri (ör. <IsSucceded>true
    </IsSucceded>) doğrudan metin (str) olarak döner, çağıran taraf
    (_call) bunu result.get("IsSucceded") ile bekliyor. Önceden buradaki
    "-> dict" tip belirteci saf Python'da (derlenmemiş .py) etkisizdi
    ama bu modül Cython ile derlenince (core/ klasörü, GitHub Actions
    release paketleri) Cython bunu ÇALIŞMA ZAMANINDA zorunlu kıldı ve
    metin döndüren yaprak düğümlerde "TypeError: Expected dict, got str"
    ile canlı ortamda patlamaya sebep oldu (2026-08-14, WhoAmI/SOAP
    yanıtı ayrıştırılırken tespit edildi) — tip belirteci bu yüzden
    kaldırıldı.
    """
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
