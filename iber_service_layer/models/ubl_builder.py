# models/ubl_builder.py
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from ..utils.ubl_tr.ubl_tr import (
    Invoice,
    UBLGenerator,
    DocumentReferenceType,
    PartyType,
    SupplierPartyType,
    PaymentMeansType,
    ExchangeRateType,
    AllowanceChargeType,
    MonetaryTotalType,
    TaxCategoryType,
    PartyIdentificationType,
    PartyNameType,
    AddressType,
    TaxSubtotalType,
    TaxTotalType,
    InvoiceLineType,
    ItemType,
    PriceType,
    PartyTaxSchemeType,
    TaxSchemeType,
    PartyLegalEntityType,
    CountryType,
)

_D2 = lambda x: str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
_D0 = lambda x: str(Decimal(x).quantize(Decimal("0"), rounding=ROUND_HALF_UP))

def _to_dec(x):
    if x is None: return Decimal("0")
    return Decimal(str(x))

def _group_by_tax(lines):
    """Satırları TaxCode (oran) bazında grupla -> { '18.00': {'base': .., 'tax': ..}, ... }"""
    groups = {}
    for ln in lines:
        base = _to_dec(ln["_LineBase"])
        tax  = _to_dec(ln["_LineTax"])
        rate = Decimal(str(ln.get("TaxCode") or 0)).quantize(Decimal("0.00"))
        k = str(rate)
        if k not in groups:
            groups[k] = {"base": Decimal("0"), "tax": Decimal("0")}
        groups[k]["base"] += base
        groups[k]["tax"]  += tax
    # finalize rounding
    for k,v in groups.items():
        v["base"] = v["base"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        v["tax"]  = v["tax"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return groups

def _calc_local(lines):
    """
    Bizim tarafta satır hesapları:
      base = qty * unit * (1 - disc%)
      tax  = base * (taxRate/100)
    """
    enriched = []
    tax_excl = Decimal("0")
    tax_tot  = Decimal("0")
    for ln in lines:
        qty  = _to_dec(ln.get("Quantity", 0))
        unit = _to_dec(ln.get("UnitPrice", 0))
        disc = _to_dec(ln.get("DiscountPercent", 0)) / Decimal("100")
        rate = _to_dec(ln.get("TaxCode", 0)) / Decimal("100")
        base = (qty * unit) * (Decimal("1") - disc)
        tax  = (base * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        base = base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax_excl += base
        tax_tot  += tax
        enriched.append({**ln, "_LineBase": base, "_LineTax": tax})
    tax_excl = tax_excl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tax_tot  = tax_tot.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tax_incl = (tax_excl + tax_tot).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return enriched, {"tax_excl": tax_excl, "tax_total": tax_tot, "tax_incl": tax_incl}

def _compare_totals(sap_totals, local_totals, tol=Decimal("0.01")):
    """Farkları uyarı listesine ekle. XML üretimini engellemez."""
    warns = []
    def _cmp(name_sap, name_local, label):
        s = _to_dec(sap_totals.get(name_sap, 0))
        l = _to_dec(local_totals.get(name_local, 0))
        if (s - l).copy_abs() > tol:
            warns.append(f"{label} sap={_D2(s)} local={_D2(l)} (tol={_D2(tol)})")
    _cmp("TaxExclusiveAmount", "tax_excl",  "TaxExclusiveAmount farkı")
    _cmp("TaxAmount",          "tax_total", "TaxAmount (KDV) farkı")
    _cmp("TaxInclusiveAmount", "tax_incl",  "TaxInclusiveAmount farkı")
    # LineExtensionAmount ve PayableAmount'ı da kontrol etmek istersen:
    if "LineExtensionAmount" in sap_totals:
        s = _to_dec(sap_totals["LineExtensionAmount"]); l = _to_dec(local_totals["tax_excl"])
        if (s - l).copy_abs() > tol:
            warns.append(f"LineExtensionAmount sap={_D2(s)} local={_D2(l)}")
    return warns

def _make_tax_subtotal(base, tax, rate, currency, tax_name="KDV", tax_code="0015", tax_scheme_id=None):
    """
    Zorunlu UBL yapısı: TaxableAmount + TaxAmount + TaxCategory(+TaxScheme)
    NOT: Bu kütüphanede TaxCategory ve TaxScheme list'tir → .values.append kullanılmalı.
    """
    sub = TaxSubtotalType()
    sub.TaxableAmount.value = _D2(base)
    sub.TaxableAmount.alg_currencyID = currency
    sub.TaxAmount.value = _D2(tax)
    sub.TaxAmount.alg_currencyID = currency

    rate_str = str(Decimal(str(rate)).quantize(Decimal("0.00")))
    rate_str = rate_str.replace('.00','') if rate_str.endswith('.00') else rate_str
    sub.Percent.value = rate_str  # "18.00", "70.00" vb.
    

    # TaxCategory (list) → içine TaxScheme (list)
    tc = TaxCategoryType()
    ts = TaxSchemeType()
    if tax_scheme_id:
        ts.ID.value = str(tax_scheme_id)
    ts.Name.value = tax_name              # örn: "KDV" / "Tevkifat"
    ts.TaxTypeCode.value = tax_code       # örn: "0015" / "WHT" / "9015"
    tc.TaxScheme.values.append(ts)        # ♻️ DİKKAT: .values.append

    sub.TaxCategory.values.append(tc)     # ♻️ DİKKAT: .values.append
    return sub


def _build_party_from_json(party_json, is_supplier=False):
    """
    JSON → UBL PartyType (XSD sıraya göre düzenlenmiş)
    """
    party = PartyType()

    # 1️⃣ PartyIdentification (VKN/TCKN zorunlu – önce geliyor)
    pid = PartyIdentificationType()
    pid.ID.alg_schemeID = party_json.get("SchemeID","").strip()
    pid.ID.value = party_json.get("SchemeValue","").strip()
    party.PartyIdentification.values.append(pid)

    # 2️⃣ PartyName (artık doğru sırada)
    pn = PartyNameType()
    pn.Name.value = (party_json.get("Title") or "").strip()
    party.PartyName.values.append(pn)

    # 3️⃣ PostalAddress
    addr_in = party_json.get("Address") or {}
    addr = AddressType()
    addr.StreetName.value = (addr_in.get("Street") or "").strip()
    addr.CityName.value   = (addr_in.get("City") or "").strip()
    addr.CitySubdivisionName.value = (addr_in.get("District") or "").strip()
    addr.PostalZone.value = (addr_in.get("PostalCode") or "").strip()
    country = CountryType()
    country.IdentificationCode.value = (addr_in.get("CountryCode") or "TR").strip()
    country.Name.value = (addr_in.get("CountryName") or "TÜRKİYE").strip()
    addr.Country.values.append(country)   
    party.PostalAddress.values.append(addr)

    # 4️⃣ PartyTaxScheme
    pts = PartyTaxSchemeType()
    pts.CompanyID.value = pid.ID.value

    ts = TaxSchemeType()
    ts.Name.value = (party_json.get("TaxOffice") or "").strip()
    ts.TaxTypeCode.value = "VAT"   # UBL’de zorunlu

    pts.TaxScheme.values.append(ts)

    party.PartyTaxScheme.values.append(pts)

    # 5️⃣ PartyLegalEntity (zorunlu değil ama doğru sırada)
    ple = PartyLegalEntityType()
    ple.RegistrationName.value = pn.Name.value
    party.PartyLegalEntity.values.append(ple)

    return party

def _append_vat_tax_totals(inv, currency, grouped, grand_tax):
    """
    Her KDV oranı için ayrı <cac:TaxTotal> + 1 adet <cac:TaxSubtotal>
    En sonda toplam KDV için ayrı <cac:TaxTotal> ekler.
    """
    calc_total = Decimal("0")
    tt = TaxTotalType()
    tt.TaxAmount.value = _D2(grand_tax)
    tt.TaxAmount.alg_currencyID = currency
    for rate, agg in grouped.items():
        
        sub = _make_tax_subtotal(
            base=agg["base"],
            tax=agg["tax"],
            rate=rate,
            currency=currency,
            tax_name="KDV",
            tax_code="0015"
        )
        tt.TaxSubtotal.values.append(sub)

        calc_total += agg["tax"]

    # Toplam KDV TaxTotal (sadece toplam vergi tutarı)
    
    inv.TaxTotal.values.append(tt)

def _append_withholding(inv, currency, w_list):
    """
    INV5/RPC5 → WithholdingTaxTotal
    - SAP 'Rate' yüzde olarak gelir (örn 70) → UBL'de "70.00" yazılır (bölme yok!)
    - TaxScheme alanlarını JSON'dan besler, yoksa güvenli varsayılanlar kullanır.
    """
    if not w_list:
        return

    wt_total = TaxTotalType()
    total_amt = Decimal("0")

    for w in w_list:
        base = _to_dec(w.get("BaseAmount", 0))
        amt  = _to_dec(w.get("WithholdingAmount", 0))
        total_amt += amt

        # SAP: 70 → UBL: "70.00"
        rate_val = _to_dec(w.get("Rate", 0))
        rate_str = str(rate_val.quantize(Decimal("0.00")))
        rate_str = rate_str.replace('.00','') if rate_str.endswith('.00') else rate_str
        tax_name = (w.get("Name") or "Tevkifat")
        tax_code = (w.get("Code") or "WHT")       # örn "9015" ya da "WHT"
        tax_id   = w.get("Code")                  # varsa ID olarak da aynı kodu bas

        sub = _make_tax_subtotal(
            base=base,
            tax=amt,
            rate=rate_str,
            currency=currency,
            tax_name=tax_name,
            tax_code=tax_code,
            tax_scheme_id=None
        )
        wt_total.TaxSubtotal.values.append(sub)

    wt_total.TaxAmount.value = _D2(total_amt)
    wt_total.TaxAmount.alg_currencyID = currency
    inv.WithholdingTaxTotal.values.append(wt_total)

def _apply_document_discount(lines, discount_dict):
    """
    Satırlara belge indirimi dağıtır.
    lines: _calc_local sonrası enriched line listesi
    discount_dict örnek:
        {
            "Value": 500.00,
            "Type": "AMOUNT",              # AMOUNT | PERCENT
            "ApplyMode": "PROPORTIONAL"    # PROPORTIONAL | EQUAL | NONE
        }
    """
    if not discount_dict:
        return lines, Decimal("0")

    disc_value = _to_dec(discount_dict.get("Value", 0))
    disc_type  = discount_dict.get("Type", "AMOUNT").upper()
    mode       = discount_dict.get("ApplyMode", "PROPORTIONAL").upper()

    # Yüzdesel indirim ise belge tutarı üzerinden hesapla
    if disc_type == "PERCENT":
        total_base = sum(l["_LineBase"] for l in lines)
        disc_value = (total_base * disc_value / Decimal("100")).quantize(Decimal("0.01"))

    if disc_value <= 0 or mode == "NONE":
        for l in lines: l["_DiscountShare"] = Decimal("0")
        return lines, Decimal("0")

    if mode == "EQUAL":
        per_line = (disc_value / len(lines)).quantize(Decimal("0.01"))
        for l in lines:
            l["_DiscountShare"] = per_line

    elif mode == "PROPORTIONAL":
        total_base = sum(l["_LineBase"] for l in lines)
        for l in lines:
            ratio = l["_LineBase"] / total_base if total_base else Decimal("0")
            l["_DiscountShare"] = (disc_value * ratio).quantize(Decimal("0.01"))

        # Yuvarlama farkını kapat → son satıra ekle
        diff = disc_value - sum(l["_DiscountShare"] for l in lines)
        if diff.copy_abs() > Decimal("0.001"):
            lines[-1]["_DiscountShare"] += diff

    # Net satır değerleri hazırla
    for l in lines:
        l["_LineBaseNet"] = (l["_LineBase"] - l["_DiscountShare"]).quantize(Decimal("0.01"))

    return lines, disc_value


def json_to_ubl_invoice(payload):
    """
    JSON → UBL Invoice()
    - SAP gönderdiği tüm tutarları (Totals) alır ve XML'e yazar
    - Biz de lokal hesap yapıp sap ile kıyaslar, warnings döndürürüz
    Return: (invoice_obj, warnings:list[str], local_totals:dict)
    """
    hdr = payload.get("Header", {})
    currency = hdr.get("Currency") or "TRY"
    lines_in = payload.get("Lines", []) or []
    withhold = payload.get("Withholding", []) or []
    sap_tot  = payload.get("Totals", {}) or {}

    # 1) Lokal satır hesapları + toplamlar
    lines_calc, local_tot = _calc_local(lines_in)

    # 2) Belge indirimi (varsa uygula)
    lines_calc, doc_discount = _apply_document_discount(lines_calc, payload.get("Discount"))

    # 2.5) Eğer indirim yoksa _LineBaseNet alanını _LineBase ile aynı yap
    for ln in lines_calc:
        if "_LineBaseNet" not in ln:
            ln["_LineBaseNet"] = ln["_LineBase"]

    # 2) UBL Invoice başlat
    inv = Invoice()
    inv.UBLVersionID.value   = hdr.get("UBLVersionID") or "2.1"
    inv.ProfileID.value      = hdr.get("ProfileID") or "TEMELFATURA"
    inv.ID.value             = hdr.get("DocNum") or ""
    inv.UUID.value           = payload.get("UUID") or hdr.get("UUID") or ""
    inv.CopyIndicator.value  = "false"
    inv.IssueDate.value      = hdr.get("DocDate") or ""
    inv.IssueTime.value = hdr.get("IssueTime") or datetime.now().strftime("%H:%M:%S")
    inv.InvoiceTypeCode.value = hdr.get("InvoiceType") or "SATIS"
    if hdr.get("Note"):
        inv.Note.value = hdr["Note"]
    inv.DocumentCurrencyCode.value = currency
    inv.PricingExchangeRate.value = hdr.get("PricingExchangeRate") or ""
    inv.LineCountNumeric.value = _D0(len(lines_in))
        # 2.4) OrderReference (sipariş bilgisi)
    order_ref = hdr.get("OrderReference") or {}
    order_id = order_ref.get("OrderID")
    if order_id:
        orf = DocumentReferenceType()
        orf.ID.value = str(order_id)
        if order_ref.get("IssueDate"):
            orf.IssueDate.value = order_ref["IssueDate"]
        inv.OrderReference.values.append(orf)

        # 2.5) DespatchDocumentReference (irsaliyeler)
    despatch_refs = hdr.get("DespatchReferences", []) or []
    for ref in despatch_refs:
        despatch_id = ref.get("DespatchID")
        if not despatch_id:
            continue

        dr = DocumentReferenceType()

      
        # Belge numarası
        dr.ID.value = str(despatch_id)

        # Tarih varsa ekle
        if ref.get("IssueDate"):
            dr.IssueDate.value = ref["IssueDate"]

        # Her irsaliye için ayrı DespatchDocumentReference ekle
        inv.DespatchDocumentReference.values.append(dr)

    # 3) AccountingSupplierParty (biz)
    #    - istersen config'ten besle; burada payload["Company"] varsa onu kullanıyoruz
    company_json = payload.get("Company") or {}
    supplier = SupplierPartyType()
    supplier.Party.values.append(_build_party_from_json(company_json, is_supplier=True))
    inv.AccountingSupplierParty.values.append(supplier)
    
   

    # 4) AccountingCustomerParty
    customer_json = payload.get("Customer") or {}
    cust = PartyType()
    cust = _build_party_from_json(customer_json)
    cparty = SupplierPartyType()  # bazı kitlerde CustomerPartyType ile aynı alanları taşır
    # NOT: Eğer sende CustomerPartyType kullanımı şartsa:
    # from ..utils.ubl_tr.ubl_tr import CustomerPartyType
    # cparty = CustomerPartyType()
    cparty.Party.values.append(cust)
    inv.AccountingCustomerParty.values.append(cparty)

    # 5) PaymentMeans (opsiyonel)
    if payload.get("Payment"):
        p = payload["Payment"]
        pm = PaymentMeansType()
        pm.PaymentMeansCode.value   = p.get("MeansCode","")
        pm.PaymentDueDate.value     = p.get("DueDate","")
        pm.PaymentChannelCode.value = p.get("ChannelCode","")
        pm.InstructionNote.value    = p.get("Note","")
        if p.get("PayeeFinancialAccount"):
            pm.PayeeFinancialAccount.ID.value = p["PayeeFinancialAccount"]
            pm.PayeeFinancialAccount.CurrencyCode.value = currency
        inv.PaymentMeans.values.append(pm)

    # 6) ExchangeRate (SAP her zaman gönderiyor demiştin)
    if hdr.get("ExchangeRate"):
        er = ExchangeRateType()
        er.SourceCurrencyCode.value = currency
        er.TargetCurrencyCode.value = "TRY"
        er.CalculationRate.value    = str(hdr["ExchangeRate"])
        inv.PricingExchangeRate.values.append(er)

    # 7) Allowance/Discount (SAP Totals içinde varsa)
    if doc_discount > 0:
        ac = AllowanceChargeType()
        ac.ChargeIndicator.value = "false"   # false = indirim
        ac.Amount.value = _D2(doc_discount)
        ac.Amount.alg_currencyID = currency
        inv.AllowanceCharge.values.append(ac)


    # 8) KDV TaxTotal (satır gruplarından)
    grouped = _group_by_tax(lines_calc)
    _append_vat_tax_totals(inv, currency, grouped, local_tot["tax_total"])

    # 9) WithholdingTaxTotal (INV5/RPC5 JSON'dan direkt)
    _append_withholding(inv, currency, withhold)

    # 10) MonetaryTotal (SAP Totals → XML)
    mt = MonetaryTotalType()
    # SAP’ten gelen varsa yaz, yoksa lokal
    line_ext = sap_tot.get("LineExtensionAmount", local_tot["tax_excl"])
    tax_exc  = sap_tot.get("TaxExclusiveAmount", local_tot["tax_excl"])
    tax_amt  = sap_tot.get("TaxAmount", local_tot["tax_total"])
    tax_inc  = sap_tot.get("TaxInclusiveAmount", local_tot["tax_incl"])
    allow = sap_tot.get("AllowanceTotalAmount", doc_discount)
    payable  = sap_tot.get("PayableAmount", tax_inc)

    mt.LineExtensionAmount.value  = _D2(line_ext); mt.LineExtensionAmount.alg_currencyID  = currency
    mt.TaxExclusiveAmount.value   = _D2(tax_exc);  mt.TaxExclusiveAmount.alg_currencyID   = currency
    mt.TaxInclusiveAmount.value   = _D2(tax_inc);  mt.TaxInclusiveAmount.alg_currencyID   = currency
    mt.AllowanceTotalAmount.value = _D2(allow);    mt.AllowanceTotalAmount.alg_currencyID = currency
    mt.PayableAmount.value        = _D2(payable);  mt.PayableAmount.alg_currencyID        = currency
    inv.LegalMonetaryTotal.values.append(mt)

    # 11) Satırlar
    for idx, ln in enumerate(lines_calc, start=1):
        il = InvoiceLineType()
        il.ID.value = str(ln.get("LineNum", idx))
        il.InvoicedQuantity.value = _D2(ln.get("Quantity", 0))
        il.InvoicedQuantity.alg_unitCode = ln.get("UnitCode") or "NIU"
        il.LineExtensionAmount.value = _D2(ln["_LineBaseNet"])
        il.LineExtensionAmount.alg_currencyID = currency
        # Item
        it = ItemType()
        it.Name.value = (ln.get("ItemName") or ln.get("ItemCode") or "")
        il.Item.values.append(it)
        # Price
        pr = PriceType()
        pr.PriceAmount.value = _D2(ln.get("UnitPrice", 0))
        pr.PriceAmount.alg_currencyID = currency
        il.Price.values.append(pr)
        
        # Satır KDV (opsiyonel ama iyi)
        # --- Satır KDV (her satır için 1 TaxTotal, 1 TaxSubtotal) ---
        line_rate = Decimal(str(ln.get("TaxCode") or 0)).quantize(Decimal("0.00"))

        t_total = TaxTotalType()
        t_total.TaxAmount.value = _D2(ln["_LineTax"])
        t_total.TaxAmount.alg_currencyID = currency

        # sadece 1 oran geldiği için direkt 1 subtotal ekle
        t_total.TaxSubtotal.values.append(
            _make_tax_subtotal(
                base = ln["_LineBase"],
                tax  = ln["_LineTax"],
                rate = line_rate,
                currency = currency
            )
        )

        il.TaxTotal.values.append(t_total)
        if ln.get("WithholdingCode"):
                wt_total = TaxTotalType()

                # tutarları decimal'e dönüştür
                base = _to_dec(ln.get("_LineTax", 0))
                amt = _to_dec(ln.get("WithholdingAmount", 0))
                rate = _to_dec(ln.get("WithholdingRate", 0))
                code = ln.get("WithholdingCode") or "9015"

                # oran string olarak yazılacak
                rate_str = str(rate.quantize(Decimal("0.00")))

                # Alt kırılım (TaxSubtotal)
                sub = _make_tax_subtotal(
                    base=base,
                    tax=amt,
                    rate=rate_str,
                    currency=currency,
                    tax_name="Tevkifat",
                    tax_code=code,
                    tax_scheme_id=code,
                )
                wt_total.TaxSubtotal.values.append(sub)

                # Üst toplam (zorunlu)
                wt_total.TaxAmount.value = _D2(amt)
                wt_total.TaxAmount.alg_currencyID = currency

                # Satıra ekle
                il.WithholdingTaxTotal.values.append(wt_total)
           

        inv.InvoiceLine.values.append(il)


       



    # 12) SAP vs lokal karşılaştırma → warnings
    warnings = _compare_totals(
        sap_totals={
            "LineExtensionAmount": sap_tot.get("LineExtensionAmount", local_tot["tax_excl"]),
            "TaxExclusiveAmount":  sap_tot.get("TaxExclusiveAmount", local_tot["tax_excl"]),
            "TaxAmount":           sap_tot.get("TaxAmount", local_tot["tax_total"]),
            "TaxInclusiveAmount":  sap_tot.get("TaxInclusiveAmount", local_tot["tax_incl"]),
        },
        local_totals={
            "tax_excl": local_tot["tax_excl"],
            "tax_total": local_tot["tax_total"],
            "tax_incl": local_tot["tax_incl"],
        },
        tol=Decimal("0.01")
    )

    return inv, warnings, local_tot
