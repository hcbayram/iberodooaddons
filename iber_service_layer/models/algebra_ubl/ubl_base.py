# -*- coding: utf-8 -*-
from odoo import models
from datetime import datetime
from decimal import Decimal,ROUND_HALF_UP
from ...utils.ubl_tr.ubl_tr import (
    Invoice,
    Despatch,
    #CreditNote,  # Artık gerçekten kullanıyoruz
    DocumentReferenceType,
    SupplierPartyType,
    CustomerPartyType,
    PartyType,
    PartyIdentificationType,
    PartyNameType,
    AddressType,
    CountryType,
    PartyTaxSchemeType,
    TaxSchemeType,
    PartyLegalEntityType,
    NoteType,
    PaymentTermsType,
    PaymentMeansType,
    FinancialAccountType,
    AttachmentType,
    ExternalReferenceType,
    PeriodType,
    BillingReferenceType,
    PersonType,ExchangeRateType
)

_D2 = lambda x: str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
_D0 = lambda x: str(Decimal(x).quantize(Decimal("0"), rounding=ROUND_HALF_UP))
_to_dec = lambda x: Decimal(str(x or 0))


class UBLBaseBuilder:
    # _name = "algebra.ubl.base"
    # _description = "UBL Base Builder (Common Logic)"

    # ---------------------------------------------------------
    # 1) Fatura/Belge oluştur (Invoice veya CreditNote)
    # ---------------------------------------------------------
    def create_document_root(self, payload):
        """
        payload["DocumentType"]:
            - "Invoice"              -> Invoice
            - "PurchaseCreditNote"   -> CreditNote
        """
        doc_type = (payload.get("DocumentType") or "Invoice").strip()

        if doc_type == "Invoice":
            return Invoice()
        elif doc_type == "Despatch":
            return Despatch()
        else:
            raise ValueError(f"Unsupported DocumentType: {doc_type}")

    # ---------------------------------------------------------
    # 2) Header doldur
    # ---------------------------------------------------------
    def build_header(self, inv, payload):
        hdr = payload.get("Header") or {}
        lines_in = payload.get("Lines", []) or []

        inv.UBLVersionID.value = hdr.get("UBLVersionID", "2.1")
        inv.ProfileID.value = hdr.get("ProfileID", "TEMELFATURA")

        inv.ID.value = hdr.get("DocNum", "") or ""
        inv.UUID.value = payload.get("UUID") or hdr.get("UUID") or ""

        inv.CopyIndicator.value = "false"

        inv.IssueDate.value = hdr.get("DocDate", "") or ""
        inv.IssueTime.value = hdr.get("IssueTime") or datetime.now().strftime("%H:%M:%S")

        inv.InvoiceTypeCode.value = hdr.get("InvoiceType", "SATIS")
        for ref in (payload.get("Notes") or []):
            if not ref.get("Note"):
                continue

            d = NoteType()
            d.alg_text = str(ref["Note"])

            inv.Note.values.append(d)

        inv.DocumentCurrencyCode.value = hdr.get("Currency", "TRY")
        if hdr.get("Currency","") != "TRY":
            exchratetag = ExchangeRateType()
            exchratetag.SourceCurrencyCode.value = hdr.get("Currency","")
            exchratetag.TargetCurrencyCode.value = "TRY"
            exchratetag.CalculationRate.value = str(hdr.get("PricingExchangeRate","1"))
            inv.PricingExchangeRate.values.append(exchratetag)
        sgk = payload.get("SGK") or None
        if sgk:
            inv.AccountingCost.value = sgk.get("sgk_fatura_tipi","")
        inv.LineCountNumeric.value = _D0(len(lines_in))
        if inv.ProfileID.value == "EARSIVFATURA":   
            ear = DocumentReferenceType()
            ear.ID.value = "ELEKTRONIK"
            ear.IssueDate.value =  hdr.get("DocDate", "") or ""
            ear.DocumentTypeCode.value = "SEND_TYPE"
            inv.AdditionalDocumentReference.values.append(ear)
        if sgk:
            adr = DocumentReferenceType()
            adr.ID.value = ""
            adr.IssueDate.value =  hdr.get("DocDate", "") or ""
            adr.DocumentTypeCode.value = "MUKELLEF_KODU"
            adr.DocumentType.value = sgk.get("sgk_sirket_kodu")
            adr.DocumentDescription.value = "SGK Mükellef Kodu"
            inv.AdditionalDocumentReference.values.append(adr)
            adr = DocumentReferenceType()
            adr.ID.value = ""
            adr.IssueDate.value =  hdr.get("DocDate", "") or ""
            adr.DocumentTypeCode.value = "MUKELLEF_ADI"
            adr.DocumentType.value = sgk.get("sgk_sirket_adi")
            adr.DocumentDescription.value = "SGK Mükellef Adı"
            inv.AdditionalDocumentReference.values.append(adr)
            adr = DocumentReferenceType()
            adr.ID.value = ""
            adr.IssueDate.value =  hdr.get("DocDate", "") or ""
            adr.DocumentTypeCode.value = "DOSYA_NO"
            adr.DocumentType.value = sgk.get("sgk_dosya_no")
            adr.DocumentDescription.value = "SGK Dosya No"
            inv.AdditionalDocumentReference.values.append(adr)

        return inv
    def _build_address(self, data):
        addr_in = data or {}
        addr = AddressType()
        addr.StreetName.value = addr_in.get("Street", "") or ""
        addr.CityName.value = addr_in.get("City", "") or ""
        addr.CitySubdivisionName.value = addr_in.get("District", "") or ""
        # UBL TR için Region genelde il
        addr.Region.value = addr_in.get("City", "") or ""
        addr.PostalZone.value = addr_in.get("PostalCode", "") or ""

        country = CountryType()
        country.IdentificationCode.value = addr_in.get("CountryCode", "TR")
        country.Name.value = addr_in.get("CountryName", "TÜRKİYE")
        addr.Country.values.append(country)

        return addr
    
    def _build_party_id(self, data):
        """
        Party Identification oluştur
        İki farklı format desteklenir:
        Format 1 (eski): {"VKN": "1234567890"} veya {"TCKN": "12345678901"}
        Format 2 (yeni): {"SchemeID": "VKN", "SchemeValue": "1234567890"}
        """
        pid = PartyIdentificationType()

        # Format 2: SchemeID ve SchemeValue varsa
        if data.get("SchemeID") and data.get("SchemeValue"):
            pid.ID.alg_schemeID = data.get("SchemeID", "").strip()
            pid.ID.value = data.get("SchemeValue", "").strip()
        # Format 1: VKN veya TCKN varsa
        elif data.get("VKN"):
            pid.ID.alg_schemeID = "VKN"
            pid.ID.value = data.get("VKN", "").strip()
        elif data.get("TCKN"):
            pid.ID.alg_schemeID = "TCKN"
            pid.ID.value = data.get("TCKN", "").strip()
        else:
            # Hiçbiri yoksa boş değerler
            pid.ID.alg_schemeID = data.get("SchemeID", "").strip()
            pid.ID.value = data.get("SchemeValue", "").strip()

        return pid
    # ---------------------------------------------------------
    # 3) Party oluştur (Supplier / Customer)
    # ---------------------------------------------------------
    def _build_party(self, data):
        """
        data:
            {
                "VKN": / "TCKN",
                "Title": ...,
                "TaxOffice": ...,
                "Address": {
                    "Street": ...,
                    "City": ...,
                    "District": ...,
                    "PostalCode": ...,
                    "CountryCode": "TR",
                    "CountryName": "TÜRKİYE",
                }
            }
        """
        party = PartyType()

        # 1) Identification
        
        pid=self._build_party_id(data)
        party.PartyIdentification.values.append(pid)
        for identification in data.get("PartyIdentifications") or []:
            add_id = PartyIdentificationType()
            add_id.ID.value = (identification.get("Value") or "").strip()
            if identification.get("SchemeID"):
                add_id.ID.alg_schemeID = identification["SchemeID"]
            party.PartyIdentification.values.append(add_id)

        # 2) Name
        pn = PartyNameType()
        pn.Name.value = (data.get("Title") or "").strip()
        party.PartyName.values.append(pn)

        # 3) Address
        

        party.PostalAddress.values.append(self._build_address(data.get("Address")))
        if data.get("PersonData"):
            pd = PersonType()
            pd.FirstName.value = data["PersonData"].get("first_name","")
            pd.FamilyName.value = data["PersonData"].get("last_name","")
            party.Person.values.append(pd)
        # 4) PartyTaxScheme
        pts = PartyTaxSchemeType()
        pts.CompanyID.value = pid.ID.value

        ts = TaxSchemeType()
        ts.Name.value = data.get("TaxOffice") or ""
        ts.TaxTypeCode.value = "VAT"  # UBL zorunlu

        pts.TaxScheme.values.append(ts)
        party.PartyTaxScheme.values.append(pts)

        # 5) LegalEntity
        ple = PartyLegalEntityType()
        ple.RegistrationName.value = pn.Name.value
        party.PartyLegalEntity.values.append(ple)

        return party

    def build_supplier(self, inv, payload):
        """
        Şirket (biz) -> AccountingSupplierParty
        """
        comp = payload.get("Company") or {}
        supplier = SupplierPartyType()
        supplier.Party.values.append(self._build_party(comp))
        inv.AccountingSupplierParty.values.append(supplier)
        return inv
    
    def getCustomerParty(self, payload):
        cust_json = payload.get("Customer") or {}
        cust = CustomerPartyType()
        cust.Party.values.append(self._build_party(cust_json))
        return cust
    
    def build_customer(self, inv, payload):
        """
        Müşteri -> AccountingCustomerParty
        Not: Bazı UBL kütüphanelerinde CustomerPartyType ayrıdır,
        senin wrapper'ını bilmediğim için SupplierPartyType kullanmaya devam ediyorum.
        """
        inv.AccountingCustomerParty.values.append(self.getCustomerParty(payload))
        return inv
    
    def build_buyer_customer(self, inv, payload):
        return inv
    def build_delivery_address(self, inv, payload):
        return inv
    
    def build_payment_means(self, inv, payload):
        """
        Ödeme Yöntemleri -> PaymentMeans
        """
        payment_means_in = payload.get("PaymentMeans") or {}
        if not payment_means_in:
            return inv


        pm = PaymentMeansType()
        pm.PaymentMeansCode.value = payment_means_in.get("PaymentMeansCode","")
        pm.PaymentDueDate.value = payment_means_in.get("PaymentDueDate","")
        pm.PaymentChannelCode.value = payment_means_in.get("PaymentChannelCode","")
        pm.InstructionNote.value = payment_means_in.get("InstructionNote","")
        pfa = FinancialAccountType()
        pfa.ID.value = payment_means_in.get("PayeeFinancialAccount","")
        pm.PayeeFinancialAccount.values.append(pfa)
        inv.PaymentMeans.values.append(pm)
        return inv
    def build_payment_terms(self, inv, payload,currency):
        """
        Ödeme Bilgileri -> PaymentTerms
        """
        payment_terms_in = payload.get("PaymentTerms") or {}
        if not payment_terms_in:
            return inv


        pt = PaymentTermsType()
        has_value = False
        if payment_terms_in.get("PaymentTermsNote",""):
            pt.Note.value = payment_terms_in.get("PaymentTermsNote","")
            has_value = True
        if payment_terms_in.get("PenaltySurchargePercent",0)>0:
            pt.PenaltySurchargePercent.value = _D2(payment_terms_in.get("PenaltySurchargePercent",0))
            has_value = True
        if payment_terms_in.get("PenaltyAmount",0)>0:
            pt.PenaltyAmount.value = _D2(payment_terms_in.get("PenaltyAmount",0))
            pt.PenaltyAmount.alg_currencyID = currency
            has_value = True
        if payment_terms_in.get("PTPaymentDueDate",""):
            pt.PaymentDueDate.value = payment_terms_in.get("PTPaymentDueDate","")
            has_value = True
        if has_value:    
            inv.PaymentTerms.values.append(pt)
        return inv
    # ---------------------------------------------------------
    # 4) Referans belgeler (İrsaliye, sipariş)
    # ---------------------------------------------------------
    def build_references(self, inv, payload):
        hdr = payload.get("Header") or {}

        # 4.1) İrsaliye (DespatchDocumentReference)
        for ref in (hdr.get("DespatchReferences") or []):
            if not ref.get("DespatchID"):
                continue

            d = DocumentReferenceType()
            d.ID.value = str(ref["DespatchID"])
            if ref.get("IssueDate"):
                d.IssueDate.value = ref["IssueDate"]

            inv.DespatchDocumentReference.values.append(d)

        # 4.2) Sipariş (OrderReference)
        # Burada kullandığın UBL wrapper'ı OrderReference için
        # doğrudan DocumentReferenceType kullanıyor olabilir.
        # Bu yüzden mevcut tipleri bozmadan minimal düzeltme yapıyorum.
        orr = hdr.get("OrderReference") or {}
        order_id = orr.get("OrderID")
        if order_id:
            o = DocumentReferenceType()
            o.ID.value = order_id
            if orr.get("IssueDate"):
                o.IssueDate.value = orr["IssueDate"]

            # Eğer nested DocumentReference göndermek istersen:
            # {
            #   "OrderReference": {
            #       "OrderID": "...",
            #       "IssueDate": "...",
            #       "DocumentReference": {
            #            "ID": "...",
            #            "IssueDate": "...",
            #            "DocumentType": "...",
            #            "DocumentDescription": "..."
            #       }
            #   }
            # }
            docref = orr.get("DocumentReference") or {}
            # Şu an kullandığın Python wrapper bu nested yapıyı
            # desteklemiyorsa bunu atlayacağız. Sadece boşa crash etmesin diye kontrol ediyoruz.
            if docref.get("ID"):
                # Eğer ubl_tr tarafında OrderReferenceType varsa,
                # oraya DocumentReferenceType append edilerek kullanılabilir.
                # Burada sadece ek bilgi amaçlı comment bırakıyorum.
                pass

            inv.OrderReference.values.append(o)

        return inv
    def build_billing_references(self, inv, payload):
        br_list = payload.get("BaseInvoicesForReturn") or []
        for br_in in br_list:
            brf = BillingReferenceType()
            b = DocumentReferenceType()
            b.ID.value = str(br_in["InvoiceNumber"])
            if br_in.get("IssueDate"):
                b.IssueDate.value = br_in["IssueDate"]
            b.DocumentTypeCode.value = "İADE"
            b.DocumentType.value = "İade Edilen Fatura"
            brf.InvoiceDocumentReference.values.append(b)
            inv.BillingReference.values.append(brf)

        return inv
    def build_okc_billing_references(self, inv, payload):
        okc = payload.get("OKC") or {}
        if not okc:
            return inv
        brf = BillingReferenceType()
        b = DocumentReferenceType()
        b.ID.value = str(okc["okc_fis_no"])
        if okc.get("okc_fis_tarih_saat"):
            b.IssueDate.value = (okc.get("okc_fis_tarih_saat") or "")[:10]
        b.DocumentTypeCode.value = "OKCBF"
        b.DocumentType.value = "OKCBilgiFisi"
        b.DocumentDescription.value = okc.get("okc_fis_tipi","")
        atch = AttachmentType()
        extref = ExternalReferenceType()
        extref.URI.value = okc.get("okc_z_rapor_no","")
        atch.ExternalReference.values.append(extref)
        b.Attachment.values.append(atch)
        vp = PeriodType()
        vp.StartDate.value = (okc.get("okc_fis_tarih_saat") or "")[:10]
        vp.StartTime.value = (okc.get("okc_fis_tarih_saat") or "")[-8:]
        b.ValidityPeriod.values.append(vp)
        iprt = PartyType()
        iprt.EndpointID.value = okc.get("okc_seri_no","")
        picls = PartyIdentificationType()
        picls.ID.value = ""
        iprt.PartyIdentification.values.append(picls)
        adrtyp = AddressType()
        adrtyp.CitySubdivisionName.value = ""
        adrtyp.CityName.value = ""
        cntrtyp = CountryType()
        cntrtyp.Name.value = ""
        adrtyp.Country.values.append(cntrtyp)
        iprt.PostalAddress.values.append(adrtyp)

        b.IssuerParty.values.append(iprt)
        brf.AdditionalDocumentReference.values.append(b)
        inv.BillingReference.values.append(brf)

        return inv

    # ---------------------------------------------------------
    # 5) Lines / Totals burada değil → shared builder yapacak
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # 6) Ana orchestrator
    # ---------------------------------------------------------
    def build_document(self, payload):
        """
        Tüm belge türleri bunu override edecek.
        Base’de boş bırakıyoruz.
        """
        raise NotImplementedError("build_document must be implemented in child class.")
