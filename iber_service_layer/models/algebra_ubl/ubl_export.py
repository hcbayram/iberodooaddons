

from odoo import models
from .ubl_invoice import InvoiceBuilder

from decimal import Decimal, ROUND_HALF_UP
from ...utils.ubl_tr.ubl_tr import (
    DeliveryType,
    DeliveryTermsType,
    ShipmentType,GoodsItemType,ShipmentStageType,TransportHandlingUnitType,PackageType,ItemInstanceType,CustomerPartyType,AddressType)

# ---------------------------------------------------------------------
# Helper formatting
# ---------------------------------------------------------------------

def _D2(x):
    return str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class ExportBuilder(InvoiceBuilder):

    def _apply_document_type_rules(self, inv, payload):
        inv.ProfileID.value = "IHRACAT"
        return inv

    def getItem(self,ln):
        res = super().getItem(ln)
        if self.profile_id == "IHRACAT":
            iit = ItemInstanceType()
            iit.ProductTraceID.value = ln.get("ProductTraceID","")
            res.ItemInstance.values.append(iit)
        return res
    def build_delivery_address(self, inv, payload):
        inv = super().build_delivery_address(inv, payload)
        if self.profile_id == "IHRACAT":
            dtyp = DeliveryType()
            datyp = AddressType()
            addr_json = payload.get("DeliveryAddress") or {}
            datyp = self._build_address(addr_json)
            dtyp.DeliveryAddress.values.append(datyp)
            inv.Delivery.values.append(dtyp)
        return inv
    
    def getBuyerParty(self, payload):
        cust_json = payload.get("Customer") or {}
        cust = CustomerPartyType()
        cust.Party.values.append(self._build_party(cust_json))
        return cust
    def build_buyer_customer(self, inv, payload):
        inv = super().build_buyer_customer(inv, payload)
        if self.profile_id == "IHRACAT":
            buyer_cust = self.getBuyerParty(payload)
            inv.BuyerCustomerParty.values.append(buyer_cust)
        return inv
    def getCustomerParty(self, payload):
        res = super().getCustomerParty(payload)
        hdr = payload.get("Header") or {}
        if self.profile_id == "IHRACAT":
            cust_json =  {
                        "SchemeID": "VKN" ,
                        "SchemeValue": "1460415308",
                        "Title": "Gümrük ve Ticaret Bakanlığı Gümrükler Genel Müdürlüğü- Bilgi İşlem Dairesi Başkanlığı",
                        "TaxOffice": "Ulus",
                        "Address": {
                            "Street": "",
                            "City": "Ankara",
                            "District": "Kadıköy",
                            "PostalCode": "",
                            "CountryCode": "TR",
                            "CountryName": "TÜRKİYE"
                            },
                        "PartyIdentifications": []
                        }
            cust = CustomerPartyType()
            cust.Party.values.append(self._build_party(cust_json))
            res = cust
        return res
    
    def getDelivery(self,ln):
        res = super().getDelivery(ln)
        if self.profile_id == "IHRACAT":
            dtyp = DeliveryType()
            
            dterms = DeliveryTermsType()
            dterms.ID.value = ln.get("IncotermCode")
            dterms.ID.alg_schemeID = "INCOTERMS"
            dtyp.DeliveryTerms.values.append(dterms)
            shp = ShipmentType()
            shp.ID.value = ""
            git = GoodsItemType()
            git.RequiredCustomsID.value = ln.get("GTIPNum")
            shp.GoodsItem.values.append(git)
            sst = ShipmentStageType()
            sst.TransportModeCode.value = ln.get("TransportType")
            shp.ShipmentStage.values.append(sst)
            thu = TransportHandlingUnitType()
            apt = PackageType()
            apt.ID.value = ln.get("ContainerNumber")
            apt.Quantity.value = _D2(ln.get("ContainerCount", 0))
            apt.PackagingTypeCode.value = ln.get("ContainerType")
            thu.ActualPackage.values.append(apt)
            shp.TransportHandlingUnit.values.append(thu)
            dtyp.Shipment.values.append(shp)
            res = dtyp

            
        return res
    

class AlgebraUBLExport(models.AbstractModel):
    _name = "algebra.ubl.export"
    _description = "UBL Export Invoice Builder Wrapper"
    _builder_class = ExportBuilder












""" class UBLEArchiveBuilder(models.AbstractModel):
    _name = "algebra.ubl.export"
    _inherit = "algebra.ubl.invoice"

    def _apply_document_type_rules(self, inv, payload):
        inv.ProfileID.value = "IHRACAT"
        return inv
    def getItem(self,ln):
        res = super().getItem(ln)
        if res.ProfileID.value == "IHRACAT":
            iit = ItemInstanceType()
            iit.ProductTraceID.value = ln.get("ProductTraceID","")
            res.ItemInstance.values.append(iit)
        return res
    def build_delivery_address(self, inv, payload):
        inv = super().build_delivery_address(inv, payload)
        if inv.ProfileID.value == "IHRACAT":
            dtyp = DeliveryType()
            datyp = AddressType()
            addr_json = payload.get("DeliveryAddress") or {}
            datyp = self._build_address(addr_json, datyp)
            dtyp.DeliveryAddress.values.append(datyp)
            inv.Delivery.values.append(dtyp)
        return inv
    def getBuyerParty(self, payload):
        cust_json = payload.get("Customer") or {}
        cust = CustomerPartyType()
        cust.Party.values.append(self._build_party(cust_json))
        return cust
    def build_buyer_customer(self, inv, payload):
        inv = super().build_buyer_customer(inv, payload)
        if inv.ProfileID.value == "IHRACAT":
            inv.BuyerCustomerParty.values.append(self.getBuyerParty(payload))
        return inv
    def getCustomerParty(self, payload):
        res = super().getCustomerParty(payload)
        hdr = payload.get("Header") or {}
        if hdr.get("ProfileID") == "IHRACAT":
            cust_json =  {
                        "VKN": "1460415308",
                        "Title": "Gümrük ve Ticaret Bakanlığı Gümrükler Genel Müdürlüğü- Bilgi İşlem Dairesi Başkanlığı",
                        "TaxOffice": "Ulus",
                        "Address": {
                            "Street": "",
                            "City": "Ankara",
                            "District": "Kadıköy",
                            "PostalCode": "",
                            "CountryCode": "TR",
                            "CountryName": "TÜRKİYE"
                            },
                        "PartyIdentifications": []
                        }
            cust = CustomerPartyType()
            cust.Party.values.append(self._build_party(cust_json))
            res = cust
        return res
    
    def getDelivery(self,ln):
        res = super().getDelivery(ln)
        if self.profile_id == "IHRACAT":
            dtyp = DeliveryType()
            
            dterms = DeliveryTermsType()
            dterms.ID.value = ln.get("IncotermCode")
            dterms.ID.alg_schemeID = "INCOTERMS"
            dtyp.DeliveryTerms.values.append(dterms)
            shp = ShipmentType()
            shp.ID.value = ""
            git = GoodsItemType()
            git.RequiredCustomsID.value = ln.get("GTIPNum")
            shp.GoodsItem.values.append(git)
            sst = ShipmentStageType()
            sst.TransportModeCode.value = ln.get("TransportType")
            shp.ShipmentStage.values.append(sst)
            thu = TransportHandlingUnitType()
            apt = PackageType()
            apt.ID.value = ln.get("ContainerNumber")
            apt.Quantity.value = _D2(ln.get("ContainerCount", 0))
            apt.PackagingTypeCode.value = ln.get("ContainerType")
            thu.ActualPackage.values.append(apt)
            shp.TransportHandlingUnit.values.append(thu)
            dtyp.Shipment.values.append(shp)
            res = dtyp

            
        return res """