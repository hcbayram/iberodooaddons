# -*- coding: utf-8 -*-
# invoice.py

from odoo import models
from .builder_shared import AlgebraUBLBuilderShared
from .ubl_base import UBLBaseBuilder

# -------------------------------------------------------
# PURE PYTHON BUILDER
# -------------------------------------------------------
class InvoiceBuilder(UBLBaseBuilder, AlgebraUBLBuilderShared):

    def __init__(self,wrapper_model, env, payload):

        self.model = wrapper_model
        self.env = env
        self.payload = payload
        hdr = payload.get("Header") or {}
        self.profile_id = hdr.get("ProfileID")
        self.currency = hdr.get("Currency", "TRY")

    def build_document(self):
        payload = self.payload
        inv = self.create_document_root(payload)

        # Header
        self.build_header(inv, payload)

        # Parties
        self.build_supplier(inv, payload)
        self.build_customer(inv, payload)
        self.build_buyer_customer(inv, payload)
        self.build_delivery_address(inv, payload)

        # Payment
        self.build_payment_means(inv, payload)
        self.build_payment_terms(inv, payload, self.currency)

        # References
        self.build_references(inv, payload)
        self.build_billing_references(inv, payload)
        self.build_okc_billing_references(inv, payload)

        # Lines
        enriched, grouped, local_totals = self.compute_lines(payload)
        self.append_lines(inv, self.currency, enriched)

        # VAT & Extra taxes
        et_list = payload.get("ExtraTaxes") or []
        self.append_vat_totals(inv, self.currency, grouped, et_list, local_totals["tax_total"])

        # Withholding
        if payload.get("Withholding"):
            self.append_withholding(inv, self.currency, payload["Withholding"])

        # Monetary Totals
        self.append_monetary_totals(inv, self.currency, local_totals, 0, enriched)

        return inv


# -------------------------------------------------------
# ODOO MODEL WRAPPER
# -------------------------------------------------------
class AlgebraUBLInvoice(models.AbstractModel):
    _name = "algebra.ubl.invoice"
    _description = "UBL Invoice Builder Wrapper"
    _builder_class = InvoiceBuilder



