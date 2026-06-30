from odoo import models, fields, api, _


class AlgebraUBLHelper(models.AbstractModel):
    _name = "algebra.ubl.json.helper"
    _description = "Shared UBL TR Helper Logic"

    def get_despatch_refs(self):
        return [
            {
                "DespatchID": d.despatch_id or "",
                "IssueDate": str(d.issue_date or ""),
            }
            for d in self.despatch_reference_ids
        ]

    def get_order_reference(self):
        self.ensure_one()
        if self.order_id:
            return {
                "OrderID": self.order_id or "",
                "IssueDate": str(self.order_issue_date or ""),
            }
        return None

    def get_invoice_notes(self):
        return [{"Note": n.note or ""} for n in self.invoice_note_ids]

    def get_header(self):
        self.ensure_one()
        from datetime import date
        despatch_refs = self.get_despatch_refs()
        order_ref = self.get_order_reference()
        return {
            "DocNum": self.id_value,
            "DocDate": str(self.issue_date or date.today()),
            "Currency": self.document_currency_id.name or "TRY",
            "PricingExchangeRate": self.document_exchange_rate or 1.0,
            "InvoiceType": self.document_type_code or "SATIS",
            "ProfileID": self.profile_id.code or "EARSIVBELGE",
            "ExchangeRate": 1,
            "Note": self.note or "",
            "UUID": getattr(self, "UUID", "") or "",
            "DespatchReferences": despatch_refs,
            "OrderReference": order_ref,
        }

    def get_company(self):
        self.ensure_one()
        company = {
            "SchemeID": "VKN" if len(self.supplier_vkn_tckn or "") == 10 else "TCKN",
            "SchemeValue": self.supplier_vkn_tckn or "",
            "Title": self.supplier_name or "",
            "TaxOffice": self.supplier_tax_office or "",
            "Address": {
                "Street": self.supplier_street or "",
                "City": self.supplier_city or "",
                "District": self.supplier_county or "",
                "PostalCode": self.supplier_postal_code or "",
                "CountryCode": self.supplier_country_code or "TR",
                "CountryName": "TÜRKİYE",
            },
            "PartyIdentifications": [
                {"SchemeID": rec.type_id.scheme_code, "Value": rec.value}
                for rec in self.supplier_extra_ids
            ],
        }
        person_data = {}
        if self.supplier_pname:
            person_data["first_name"] = self.supplier_pname
        if self.supplier_psurname:
            person_data["last_name"] = self.supplier_psurname
        if person_data:
            company["PersonData"] = person_data
        return company

    def get_customer(self):
        self.ensure_one()
        scheme_id = "VKN" if len(self.customer_vkn_tckn or "") == 10 else "TCKN"
        scheme_value = self.customer_vkn_tckn or ""
        if self.profile_id.code == "IHRACAT":
            scheme_id = "PARTYTYPE"
            scheme_value = "EXPORT"
        customer = {
            "SchemeID": scheme_id,
            "SchemeValue": scheme_value,
            "Title": self.customer_name or "",
            "TaxOffice": self.customer_tax_office or "",
            "Address": {
                "Street": self.customer_street or "",
                "City": self.customer_city or "",
                "District": self.customer_county or "",
                "PostalCode": self.customer_postal_code or "",
                "CountryCode": self.customer_country_code or "TR",
                "CountryName": "TÜRKİYE",
            },
            "PartyIdentifications": [
                {"SchemeID": rec.type_id.scheme_code, "Value": rec.value}
                for rec in self.customer_extra_ids
            ],
        }
        person_data = {}
        if self.customer_pname:
            person_data["first_name"] = self.customer_pname
        if self.customer_psurname:
            person_data["last_name"] = self.customer_psurname
        if person_data:
            customer["PersonData"] = person_data
        return customer

    def get_payment_means(self):
        self.ensure_one()
        payment_means = {
            "PaymentMeansCode": self.PaymentMeansCode,
            "PaymentDueDate": str(self.PaymentDueDate) if self.PaymentDueDate else None,
            "PaymentChannelCode": self.PaymentChannelCode,
            "InstructionNote": self.InstructionNote,
            "PayeeFinancialAccount": self.PayeeFinancialAccount,
        }
        if self.PaymentMeansCode and self.PayeeFinancialAccount:
            return payment_means
        return {}

    def get_payment_terms(self):
        self.ensure_one()
        return {
            "PaymentTermsNote": self.PaymentTermsNote or "",
            "PenaltySurchargePercent": self.PenaltySurchargePercent,
            "PenaltyAmount": self.PenaltyAmount,
            "PTPaymentDueDate": str(self.PTPaymentDueDate) if self.PTPaymentDueDate else None,
        }

    def get_okc(self):
        self.ensure_one()
        okc_raw = {
            "okc_fis_no": self.okc_fis_no,
            "okc_fis_tarih_saat": str(self.okc_fis_tarih_saat) if self.okc_fis_tarih_saat else None,
            "okc_z_rapor_no": self.okc_z_rapor_no,
            "okc_seri_no": self.okc_seri_no,
            "okc_fis_tipi": self.okc_fis_tipi,
        }
        return okc_raw if all(okc_raw.values()) else {}

    def get_sgk_info(self):
        self.ensure_one()
        sgk_raw = {
            "sgk_fatura_tipi": self.sgk_invoice_type,
            "sgk_sirket_kodu": self.sgk_company_code,
            "sgk_sirket_adi": self.sgk_company_name,
            "sgk_dosya_no": self.sgk_file_number,
        }
        return sgk_raw if all(sgk_raw.values()) else {}

    def get_lines(self):
        lines = []
        for idx, line in enumerate(self.line_ids):
            line_notes = [{"Note": n.note or ""} for n in line.line_note_ids]
            extra_taxes = [
                {
                    "Code": xt.tax_type_id.code,
                    "Name": xt.tax_type_id.name,
                    "Type": xt.tax_type_id.type,
                    "BaseAmount": xt.taxable_amount,
                    "Rate": xt.rate,
                    "Amount": xt.amount,
                }
                for xt in line.taxextra_ids
            ]
            lines.append(self.build_ubl_line_dict(line=line, idx=idx, line_notes=line_notes, extra_taxes=extra_taxes))
        return lines

    def build_ubl_line_dict(self, line, idx, line_notes="", extra_taxes=None):
        extra_taxes = extra_taxes or []
        return {
            "LineNum": idx + 1,
            "ItemCode": line.name or "",
            "ItemName": line.name or "",
            "Quantity": line.quantity,
            "UnitPrice": line.price_amount,
            "DiscountPercent": 0,
            "TaxExemptionReasonId": line.tax_exemption_reason_id.code,
            "TaxExemptionReason": line.tax_exemption_reason_id.name,
            "TaxCode": int(line.tax_percent or 0),
            "UnitCode": line.unit_code or "NIU",
            "WithholdingRate": line.withholding_rate or 0.0,
            "WithholdingAmount": line.withholding_amount or 0.0,
            "WithholdingCode": line.withholding_code or "",
            "Notes": line_notes,
            "ExtraTaxes": extra_taxes,
            "Adjustments": [
                {
                    "Type": adj.type.upper(),
                    "Rate": adj.rate or 0.0,
                    "Amount": adj.amount or 0.0,
                    "BaseAmount": adj.base_amount or 0.0,
                    "Description": adj.description or "",
                }
                for adj in line.adjustment_ids
            ],
            "Description": line.description or "",
            "BrandName": line.brandName or "",
            "ModelName": line.modelName or "",
            "BuyersItemIdentification": line.buyersItemId or "",
            "SellersItemIdentification": line.sellersItemId or "",
            "ManufacturersItemIdentification": line.manufacturerItemId or "",
        }

    def get_total_amounts(self):
        self.ensure_one()
        return {
            "LineExtensionAmount": self.line_extension_total or 0.0,
            "TaxExclusiveAmount": self.total_without_tax or 0.0,
            "TaxAmount": self.tax_total_amount or 0.0,
            "TaxInclusiveAmount": self.total_with_tax or 0.0,
            "PayableAmount": self.payable_amount or 0.0,
        }

    def get_withholding_totals(self):
        self.ensure_one()
        return [
            {
                "BaseAmount": wt.taxable_amount,
                "WithholdingAmount": wt.tax_amount,
                "Rate": wt.percent,
                "Name": wt.tax_scheme_name,
                "Code": wt.tax_scheme_code,
            }
            for wt in self.subtotal_ids.filtered(lambda s: s.kind == "withholding_vat")
        ]

    def get_extra_taxes_summary(self):
        self.ensure_one()
        return [
            {
                "BaseAmount": et.taxable_amount,
                "Amount": et.tax_amount,
                "Rate": et.percent,
                "Name": et.tax_scheme_name,
                "Code": et.tax_scheme_code,
            }
            for et in self.subtotal_ids.filtered(lambda s: s.kind == "others")
        ]

    def get_discount(self):
        self.ensure_one()
        return {
            "DocumentDiscountAmount": self.allowance_total_amount or 0.0,
            "Method": "PROPORTIONAL",
        }

    def get_billing_reference(self):
        self.ensure_one()
        return [
            {
                "InvoiceNumber": base_invoice.invoice_number or "",
                "IssueDate": str(base_invoice.issue_date or ""),
            }
            for base_invoice in self.return_reference_ids
        ]
