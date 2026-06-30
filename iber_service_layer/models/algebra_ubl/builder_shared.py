# -*- coding: utf-8 -*-
from odoo import models
from decimal import Decimal, ROUND_HALF_UP
from ...utils.ubl_tr.ubl_tr import (
    TaxTotalType,
    TaxSubtotalType,
    TaxSchemeType,
    TaxCategoryType,
    InvoiceLineType,
    ItemType,
    PriceType,
    MonetaryTotalType,
    NoteType,
    AllowanceChargeType,
    ItemIdentificationType,
)

# ---------------------------------------------------------------------
# Helper formatting
# ---------------------------------------------------------------------

def _D2(x):
    return str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _D0(x):
    return str(Decimal(x).quantize(Decimal("0"), rounding=ROUND_HALF_UP))

def _to_dec(x):
    if x is None:
        return Decimal("0")
    return Decimal(str(x))


class AlgebraUBLBuilderShared:
    # _name = "algebra.ubl.builder.shared"
    # _description = "Shared UBL TR Builder Logic"

    # ------------------------------------------------------------
    # 1) LOCAL LINE CALCULATIONS
    # ------------------------------------------------------------
    def compute_lines(self, payload):
        """
        Tam hesaplama:
        - Satır matrah
        - Satır KDV
        - Satır tevkifat
        - Belge indirimi
        - Ek masraf
        - PayableAmount (Net ödenecek)
        """

        lines_in = payload.get("Lines") or []
        enriched = []
        tax_excl = Decimal("0")
        tax_tot = Decimal("0")
        withholding_total = Decimal("0")

        # -------------------------
        # 1) Belge indirimi (Discount)
        # -------------------------
        doc_disc = payload.get("Discount") or {}
        doc_disc_value = _to_dec(doc_disc.get("Value", 0))
        doc_disc_type = (doc_disc.get("Type") or "").upper()  # AMOUNT | PERCENT
        doc_disc_apply = (doc_disc.get("ApplyMode") or "PROPORTIONAL").upper()

        # -------------------------
        # 2) Tevkifat bilgisi
        # -------------------------
        wht_percent = 0
        if payload.get("Withholding"):
            wht = payload.get("Withholding")[0] or {}
            wht_percent = _to_dec(wht.get("Rate", 0)) / Decimal("100")
            wht_base_mode = (wht.get("Base") or "TAX").upper()  # BASE | TAX

        # -------------------------
        # 3) Satır Hesapları
        # -------------------------
        for ln in lines_in:
            qty = _to_dec(ln.get("Quantity", 0))
            price = _to_dec(ln.get("UnitPrice", 0))
            disc = _to_dec(ln.get("DiscountPercent", 0)) / Decimal("100")
            
            
            rate = _to_dec(ln.get("TaxCode", 0)) / Decimal("100")

            # Satır matrahı
            base = (qty * price) * (1 - disc)
            base = base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            allowance_total = Decimal("0")
            if ln.get("Adjustments"):
                for adjustment in ln.get("Adjustments"):
                    if (adjustment.get("Type") or "").upper() == "DISCOUNT":
                        base -= _to_dec(adjustment.get("Amount", 0))
                        allowance_total += _to_dec(adjustment.get("Amount", 0))
                    else:
                        base += _to_dec(adjustment.get("Amount", 0))
                        allowance_total -=  _to_dec(adjustment.get("Amount", 0))
            # Satır KDV'si
            tax = (base * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            taxtotal = tax
            if ln.get("ExtraTaxes"):
                for ext_tax in ln.get("ExtraTaxes"):
                    ext_rate = _to_dec(ext_tax.get("Rate", 0)) / Decimal("100")
                    ext_base = base
                    if ext_tax.get("Type") == "base":
                        ext_base = _to_dec(ext_tax.get("BaseAmount", 0))
                    ext_amt = (ext_base * ext_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    taxtotal += ext_amt

            # Satır tevkifatı
            wht_amount = 0
            if payload.get("Withholding"):
                if wht_percent > 0:
                    if wht_base_mode == "BASE":
                        wht_amount = (base * wht_percent).quantize(Decimal("0.01"))
                    else:
                        wht_amount = (tax * wht_percent).quantize(Decimal("0.01"))
                else:
                    wht_amount = Decimal("0")

                withholding_total += wht_amount

            enriched.append({
                **ln,
                "_LineBase": base,
                "_LineTax": tax,
                "_LineTotTax":taxtotal,
                "_LineWithholdingAmount": wht_amount,
            })

            tax_excl += base
            tax_tot += taxtotal

        # ------------------------------------
        # 4) Belge İndirimi Toplamı (Discount)
        # ------------------------------------
        """ allowance_total = Decimal("0")

        if doc_disc_value > 0:
            if doc_disc_type == "AMOUNT":
                allowance_total = doc_disc_value
            elif doc_disc_type == "PERCENT":
                allowance_total = (tax_excl * (doc_disc_value / Decimal("100")))
                allowance_total = allowance_total.quantize(Decimal("0.01")) """

        # ------------------------------------
        # 5) Masraf (Charge)
        # ------------------------------------
        charge_total = Decimal("0")
        if payload.get("Charges"):
            for ch in payload["Charges"]:
                amt = _to_dec(ch.get("Amount", 0))
                charge_total += amt

        # ------------------------------------
        # 6) Temel toplamlar
        # ------------------------------------
        tax_incl = tax_excl + tax_tot
        line_extension_total = tax_excl + allowance_total
        local_totals = {
            "line_extension_total":line_extension_total.quantize(Decimal("0.01")),
            "tax_excl": tax_excl.quantize(Decimal("0.01")),
            "tax_total": tax_tot.quantize(Decimal("0.01")),
            "tax_incl": tax_incl.quantize(Decimal("0.01")),
            "withholding_total": withholding_total.quantize(Decimal("0.01")),
            "allowance_total": allowance_total.quantize(Decimal("0.01")),
            "charge_total": charge_total.quantize(Decimal("0.01")),
        }

        # ------------------------------------
        # 7) NET ÖDENECEK TUTAR (PayableAmount)
        # ------------------------------------
        payable_amount = (
            tax_excl
            + tax_tot
            - withholding_total
            + charge_total
        ).quantize(Decimal("0.01"))

        local_totals["payable_amount"] = payable_amount

        # ------------------------------------
        # 8) Vergi Oranına + İstisna Koduna Göre Gruplama
        # ------------------------------------
        grouped = {}

        for ln in enriched:
            rate = Decimal(str(ln.get("TaxCode") or 0)).quantize(Decimal("0.00"))
            rate_str = str(rate)

            exemption = ln.get("TaxExemptionReasonId") or None
            exemption_str = str(exemption) if exemption not in (None, "", 0) else "None"
            exemptiontext = ln.get("TaxExemptionReason") or ""
            # Anahtar artık ikili
            key = f"{rate_str}-{exemption_str}"

            if key not in grouped:
                grouped[key] = {
                    "rate": rate,
                    "exemption": exemption,   # orijinal değer
                    "exemptiontext": exemptiontext,   # orijinal değer
                    "base": Decimal("0"),
                    "tax": Decimal("0"),
                }

            grouped[key]["base"] += ln["_LineBase"]
            grouped[key]["tax"]  += ln["_LineTax"]

        # yuvarlama
        for k, v in grouped.items():
            v["base"] = v["base"].quantize(Decimal("0.01"))
            v["tax"]  = v["tax"].quantize(Decimal("0.01"))


        return enriched, grouped, local_totals

    # ------------------------------------------------------------
    # 2) MAKE TAX SUBTOTAL (KDV & TEVKIFAT)
    # ------------------------------------------------------------
    def make_tax_subtotal(
        self, *, base, tax, rate, currency,
        tax_name="KDV", tax_code="0015", tax_scheme_id=None,tax_exemption_code=None,tax_exemption_reason=None
    ):
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
        if tax_exemption_code and tax_exemption_reason:
            tc.TaxExemptionReasonCode.value = tax_exemption_code
            tc.TaxExemptionReason.value = tax_exemption_reason
        ts = TaxSchemeType()
        if tax_scheme_id:
            ts.ID.value = str(tax_scheme_id)
        ts.Name.value = tax_name              # örn: "KDV" / "Tevkifat"
        ts.TaxTypeCode.value = tax_code       # örn: "0015" / "WHT" / "9015"
        tc.TaxScheme.values.append(ts)        # ♻️ DİKKAT: .values.append

        sub.TaxCategory.values.append(tc)     # ♻️ DİKKAT: .values.append
        return sub

    # ------------------------------------------------------------
    # 3) APPEND: VAT TAX TOTALS (KDV)
    # ------------------------------------------------------------
    def append_vat_totals(self, inv, currency, grouped,et_list, grand_tax):
        """
        Her KDV oranı için ayrı <cac:TaxTotal> + 1 adet <cac:TaxSubtotal>
        En sonda toplam KDV için ayrı <cac:TaxTotal> ekler.
        """
        calc_total = Decimal("0")
        tt = TaxTotalType()
        tt.TaxAmount.value = _D2(grand_tax)
        tt.TaxAmount.alg_currencyID = currency
        for rate, agg in grouped.items():
            rate = agg["rate"]
            exemption = agg["exemption"]
            exemptiontext = agg["exemptiontext"]
            base = agg["base"]
            tax  = agg["tax"]
            
            sub = self.make_tax_subtotal(
                base=agg["base"],
                tax=agg["tax"],
                rate=rate,
                currency=currency,
                tax_name="KDV",
                tax_code="0015",
                tax_exemption_code=exemption,
                tax_exemption_reason=exemptiontext,
            )
            tt.TaxSubtotal.values.append(sub)

        for et in et_list:
            base = _to_dec(et.get("BaseAmount", 0))
            amt  = _to_dec(et.get("Amount", 0))
            

            rate_val = _to_dec(et.get("Rate", 0))
            rate_str = str(rate_val.quantize(Decimal("0.00")))
            rate_str = rate_str.replace('.00','') if rate_str.endswith('.00') else rate_str
            tax_name = (et.get("Name") or "Ek Vergi")
            tax_code = (et.get("Code") or "9999")
            tax_id   = et.get("Code")

            sub = self.make_tax_subtotal(
                base=base,
                tax=amt,
                rate=rate_str,
                currency=currency,
                tax_name=tax_name,
                tax_code=tax_code,
                tax_scheme_id=None
            )
            tt.TaxSubtotal.values.append(sub)

        # Toplam KDV TaxTotal (sadece toplam vergi tutarı)
        
        inv.TaxTotal.values.append(tt)
        

    # ------------------------------------------------------------
    # 4) APPEND: WITHHOLDING (TEVKİFAT)
    # ------------------------------------------------------------
    def append_withholding(self, inv, currency, w_list):
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

            sub = self.make_tax_subtotal(
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
    # ------------------------------------------------------------
    # 4.5) APPEND: EXTRA TAXES
    # ------------------------------------------------------------
    def append_extra_taxes(self, inv, currency, et_list):
        """
        INV5/RPC5 → ExtraTaxTotal
        - Ek Vergi türünde vergiler için kullanılır.
        - TaxScheme alanlarını JSON'dan besler, yoksa güvenli varsayılanlar kullanır.
        """
        if not et_list:
            return

        et_total = TaxTotalType()
        total_amt = Decimal("0")

        for et in et_list:
            base = _to_dec(et.get("BaseAmount", 0))
            amt  = _to_dec(et.get("Amount", 0))
            total_amt += amt

            rate_val = _to_dec(et.get("Rate", 0))
            rate_str = str(rate_val.quantize(Decimal("0.00")))
            rate_str = rate_str.replace('.00','') if rate_str.endswith('.00') else rate_str
            tax_name = (et.get("Name") or "Ek Vergi")
            tax_code = (et.get("Code") or "9999")
            tax_id   = et.get("Code")

            sub = self.make_tax_subtotal(
                base=base,
                tax=amt,
                rate=rate_str,
                currency=currency,
                tax_name=tax_name,
                tax_code=tax_code,
                tax_scheme_id=None
            )
            et_total.TaxSubtotal.values.append(sub)

        et_total.TaxAmount.value = _D2(total_amt)
        et_total.TaxAmount.alg_currencyID = currency
        inv.TaxTotal.values.append(et_total)
    # ------------------------------------------------------------
    # 5) APPEND INVOICE LINES
    # ------------------------------------------------------------
    def getDelivery(self,ln):
        return None
    def getItem(self, ln):
        """
        Satırdan ItemType oluşturur.
        """
        it = ItemType()
        it.Name.value =  ln.get("ItemName") or ""
        it.Description.value = ln.get("Description") or ""
        it.BrandName.value = ln.get("BrandName") or "" 
        it.ModelName.value = ln.get("ModelName") or ""
        bit = ItemIdentificationType()
        bit.ID.value = ln.get("BuyersItemIdentification") or ""
        it.BuyersItemIdentification.values.append(bit)
        s_it = ItemIdentificationType()
        s_it.ID.value = ln.get("SellersItemIdentification") or ""
        it.SellersItemIdentification.values.append(s_it)
        m_it = ItemIdentificationType()
        m_it.ID.value = ln.get("ManufacturersItemIdentification") or ""
        it.ManufacturersItemIdentification.values.append(m_it)
        a_it = ItemIdentificationType()
        a_it.ID.value = ln.get("AdditionalItemIdentification") or ""
        it.AdditionalItemIdentification.values.append(a_it) 

        return it
    def append_lines(self, inv, currency, enriched):
        """
        enriched: compute_lines çıktısı (her satırda _LineBase, _LineTax var)
        """
        for idx, ln in enumerate(enriched, start=1):
            il = InvoiceLineType()

            il.ID.value = str(ln.get("LineNum", idx))

            il.InvoicedQuantity.value = _D2(ln.get("Quantity", 0))
            il.InvoicedQuantity.alg_unitCode = ln.get("UnitCode") or "NIU"

            il.LineExtensionAmount.value = _D2(ln["_LineBase"])
            il.LineExtensionAmount.alg_currencyID = currency
            delivery = self.getDelivery(ln)
            if delivery:
                il.Delivery.values.append(delivery)
                        # ----------------------------------------------------
            # Satır bazlı Discount/Surcharge (İndirim & Arttırım)
            # ln["Adjustments"] formatı:
            # [
            #   {
            #       "Type": "DISCOUNT" / "SURCHARGE",
            #       "Amount": 500,
            #       "BaseAmount": 5000,
            #       "Factor": 0.1,      # => MultiplierFactorNumeric
            #       "Sequence": 1,      # opsiyonel
            #       "Reason": "..."     # opsiyonel
            #   },
            #   ...
            # ]
            # ----------------------------------------------------
            if ln.get("Adjustments"):
                for idx_adj, adj in enumerate(ln.get("Adjustments") or [], start=1):
                    amt = _to_dec(adj.get("Amount", 0))
                    if amt == 0:
                        continue

                    base_amt = _to_dec(
                        adj.get("BaseAmount",
                                ln.get("_LineBaseNet") or ln.get("_LineBase") or 0)
                    )
                    factor = adj.get("Rate") / 100 if adj.get("Rate") is not None else None
                    seq = adj.get("Sequence") or idx_adj
                    reason = adj.get("Description") or None

                    adj_type = (adj.get("Type") or "DISCOUNT").upper()  # SURCHARGE | DISCOUNT

                    ac = AllowanceChargeType()

                    # ChargeIndicator: true = SURCHARGE, false = DISCOUNT
                    ac.ChargeIndicator.value = "true" if adj_type == "SURCHARGE" else "false"

                    # MultiplierFactorNumeric (varsa)
                    if factor is not None:
                        factor_dec = _to_dec(factor)
                        # UBL örneğinde 0.1 gibi → istersen düz string yazabiliriz
                        ac.MultiplierFactorNumeric.value = str(
                            factor_dec.normalize()
                        )

                    # SequenceNumeric (opsiyonel)
                    if seq is not None:
                        try:
                            ac.SequenceNumeric.value = str(int(seq))
                        except Exception:
                            ac.SequenceNumeric.value = "1"

                    # Amount
                    ac.Amount.value = _D2(amt)
                    ac.Amount.alg_currencyID = currency

                    # BaseAmount
                    ac.BaseAmount.value = _D2(base_amt)
                    ac.BaseAmount.alg_currencyID = currency

                    # Reason (AllowanceChargeReason) varsa
                    if reason:
                        # çoğu UBL lib'inde: AllowanceChargeReason.value
                        try:
                            ac.AllowanceChargeReason.value = reason
                        except Exception:
                            # wrapper farklıysa sessiz geç
                            pass

                    # InvoiceLine içindeki AllowanceCharge listesine ekle
                    il.AllowanceCharge.values.append(ac)


            it = self.getItem(ln)
            il.Item.values.append(it)

            pr = PriceType()
            pr.PriceAmount.value = _D2(ln.get("UnitPrice", 0))
            pr.PriceAmount.alg_currencyID = currency
            il.Price.values.append(pr)

            # Line VAT
            rate = Decimal(str(ln.get("TaxCode") or 0)).quantize(Decimal("0.00"))

            t_total = TaxTotalType()
            t_total.TaxAmount.value = _D2(ln["_LineTotTax"])
            t_total.TaxAmount.alg_currencyID = currency

            t_total.TaxSubtotal.values.append(
                self.make_tax_subtotal(
                    base=ln["_LineBase"],
                    tax=ln["_LineTax"],
                    rate=rate,
                    currency=currency,
                    tax_name="KDV",
                    tax_code="0015",
                    tax_exemption_code=ln.get("TaxExemptionReasonId"),
                    tax_exemption_reason=ln.get("TaxExemptionReason"),
                )
            )

                
            if ln.get("ExtraTaxes"):
                for ext_tax in (ln.get("ExtraTaxes") or []):
                    ext_base = 0
                    if ext_tax.get("Type")=="base":
                        ext_base = _to_dec(ext_tax.get("BaseAmount", 0))
                    ext_amt = _to_dec(ext_tax.get("Amount", 0))
                    ext_rate = _to_dec(ext_tax.get("Rate", 0))
                    
                   
                    t_total.TaxAmount.value = _D2(ext_amt)
                    t_total.TaxAmount.alg_currencyID = currency
                    ext_sub = self.make_tax_subtotal(
                        base=ext_base,
                        tax=ext_amt,
                        rate=ext_rate,
                        currency=currency,
                        tax_name=ext_tax.get("Name") or "Ek Vergi",
                        tax_code=ext_tax.get("Code") or "9999",
                        tax_scheme_id=ext_tax.get("Code"),
                    )

                    
                    t_total.TaxSubtotal.values.append(ext_sub)

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
                sub = self.make_tax_subtotal(
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

            if ln.get("Notes"):
                for ref in (ln.get("Notes") or []):
                    if not ref.get("Note"):
                        continue

                    d = NoteType()
                    d.alg_text = str(ref["Note"])

                    il.Note.values.append(d)
            inv.InvoiceLine.values.append(il)

    # ------------------------------------------------------------
    # 6) APPEND MONETARY TOTALS
    # ------------------------------------------------------------
    def append_monetary_totals(self, inv, currency, totals, discount, enriched=None):
        """
        totals: compute_lines local_totals çıktısı
        discount: belge bazlı toplam iskonto (TRY)
        """
        mt = MonetaryTotalType()

        mt.LineExtensionAmount.value = _D2(totals["line_extension_total"])
        mt.LineExtensionAmount.alg_currencyID = currency

        mt.TaxExclusiveAmount.value = _D2(totals["tax_excl"])
        mt.TaxExclusiveAmount.alg_currencyID = currency

        mt.TaxInclusiveAmount.value = _D2(totals["tax_incl"])
        mt.TaxInclusiveAmount.alg_currencyID = currency

        # ---------------------------
        # 2) Tüm indirim & arttırımları topla
        # ---------------------------
        allowance_sum = Decimal("0")
        charge_sum = Decimal("0")

        # 2.1 Satır içi line discount
        if enriched:
            for l in enriched:
                # Satır indirimi
                allowance_sum += _to_dec(l.get("_LineDiscountLocal", 0))

                # Satıra belge indirimi payı
                allowance_sum += _to_dec(l.get("_DiscountShare", 0))

                # Line-level Adjustments
                for adj in l.get("Adjustments", []) or []:
                    amt = _to_dec(adj.get("Amount", 0))
                    if amt == 0:
                        continue
                    adj_type = (adj.get("Type") or "SURCHARGE").upper()

                    if adj_type == "DISCOUNT":
                        allowance_sum += amt
                    else:
                        charge_sum += amt

        # 2.2 Document-level discount
        allowance_sum += _to_dec(totals.get("doc_discount", 0))

        # ---------------------------
        # 3) Net Allowance Total Amount
        # ---------------------------
        net_allowance = allowance_sum - charge_sum

        mt.AllowanceTotalAmount.value = _D2(net_allowance)
        mt.AllowanceTotalAmount.alg_currencyID = currency

        payable = totals["payable_amount"] 
        mt.PayableAmount.value = _D2(payable)
        mt.PayableAmount.alg_currencyID = currency

        inv.LegalMonetaryTotal.values.append(mt)
