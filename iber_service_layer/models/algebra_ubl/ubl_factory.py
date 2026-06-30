# -*- coding: utf-8 -*-
# algebra/ubl/factory.py
from odoo import models

class UBLBuilderFactory(models.AbstractModel):
    _name = "algebra.ubl.factory"
    _description = "Select proper UBL builder"

    def get_mapper(self, payload):
        hdr = payload.get("Header") or {}
        doc_type = payload.get("DocumentType", "Invoice")
        profile = (hdr.get("ProfileID") or "TEMELFATURA").upper()

        # 1) SAP doküman tipi
        if doc_type in ("Despatch", "DespatchAdvice"):
            model = self.env["algebra.ubl.despatch"]
        elif doc_type == "PurchaseCreditNote":
            model = self.env["algebra.ubl.creditnote"]
        else:
            # 2) Profile
            if profile in ("TEMELFATURA", "TICARIFATURA"):
                model = self.env["algebra.ubl.invoice"]
            elif profile == "EARSIVFATURA":
                model = self.env["algebra.ubl.earchive"]
            elif profile in ("IHRACAT", "EXPORT"):
                model = self.env["algebra.ubl.export"]
            else:
                model = self.env["algebra.ubl.invoice"]

        Builder = model._builder_class   # ← gerçek python sınıfı
        builder = Builder(model, self.env, payload)
        return builder














""" from odoo import models

class UBLBuilderFactory(models.AbstractModel):
    _name = "algebra.ubl.factory"
    _description = "Factory for selecting proper UBL builder"

    def get_mapper(self, payload):
        
        hdr = payload.get("Header") or {}
        doc_type = payload.get("DocumentType", "Invoice")
        profile = (hdr.get("ProfileID") or "TEMELFATURA").upper()

        # Önce DocumentType'a göre ayıralım (örn: CreditNote)
        if doc_type == "PurchaseCreditNote":
            return self.env["algebra.ubl.creditnote"]

        # Sonra profile'a göre invoice builder seçelim
        if profile in ("TEMELFATURA", "TICARIFATURA"):
            return self.env["algebra.ubl.invoice"]

        if profile == "EARSIVFATURA":
            return self.env["algebra.ubl.earchive"]

        if profile in ("IHRACAT", "EXPORT"):
            return self.env["algebra.ubl.export"]

        # Default
        return self.env["algebra.ubl.invoice"] """
