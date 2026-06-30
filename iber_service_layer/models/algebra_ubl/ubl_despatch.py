# -*- coding: utf-8 -*-
# ubl_despatch.py

from odoo import models
from datetime import datetime
from .ubl_base import UBLBaseBuilder
from ...utils.ubl_tr.ubl_tr import (
    Despatch,
    DespatchLineType,
    DespatchType,
    ItemType,
    ItemIdentificationType,
    ShipmentType,
    ShipmentStageType,
    DeliveryType,
    ConsignmentType,
    TransportHandlingUnitType,
    TransportEquipmentType,
    TransportMeansType,
    RoadTransportType,
    GoodsItemType,
    OrderLineReferenceType,
    DocumentReferenceType,
    NoteType,
    CustomerPartyType,
    SupplierPartyType,
    ContactType,
    PersonType,
)
from decimal import Decimal, ROUND_HALF_UP

_D2 = lambda x: str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
_D0 = lambda x: str(Decimal(x).quantize(Decimal("0"), rounding=ROUND_HALF_UP))
_to_dec = lambda x: Decimal(str(x or 0))


class DespatchBuilder(UBLBaseBuilder):
    """
    DespatchAdvice (İrsaliye) Builder
    Invoice builder'dan farklı olarak:
    - Fiyat/vergi hesapları YOK
    - Miktar (Quantity) odaklı
    - Teslimat bilgileri (Shipment, Delivery) VAR
    """

    def __init__(self, wrapper_model, env, payload):
        self.model = wrapper_model
        self.env = env
        self.payload = payload
        hdr = payload.get("Header") or {}
        self.profile_id = hdr.get("ProfileID", "TEMELIRSALIYE")

    def build_document(self):
        """
        DespatchAdvice belgesi oluştur
        XSD element sırası (ZORUNLU):
        1. Header (UBLVersionID, CustomizationID, ProfileID, ID, UUID, IssueDate, IssueTime, etc.)
        2. OrderReference (opsiyonel)
        3. AdditionalDocumentReference (opsiyonel)
        4. DespatchSupplierParty (zorunlu)
        5. DeliveryCustomerParty (zorunlu)
        6. BuyerCustomerParty (opsiyonel)
        7. SellerSupplierParty (opsiyonel)
        8. Shipment (zorunlu)
        9. DespatchLine (zorunlu)
        """
        payload = self.payload
        desp = self.create_despatch_root(payload)

        # 1) Header (UBLVersionID, ProfileID, ID, UUID, IssueDate, IssueTime, Note, LineCountNumeric)
        self.build_despatch_header(desp, payload)

        # 2) References - XSD'de parties'den ÖNCE!
        self.build_despatch_references(desp, payload)

        # 3-6) Parties (DespatchAdvice specific - XSD sırası önemli!)
        self.build_despatch_supplier(desp, payload)       # 3) DespatchSupplierParty (zorunlu)
        self.build_delivery_customer(desp, payload)       # 4) DeliveryCustomerParty (zorunlu)
        self.build_buyer_customer(desp, payload)          # 5) BuyerCustomerParty (opsiyonel)
        self.build_seller_supplier(desp, payload)         # 6) SellerSupplierParty (opsiyonel)

        # 7) Shipment (Sevkiyat bilgileri - zorunlu)
        self.build_shipment(desp, payload)

        # 8) Lines (DespatchLine - zorunlu)
        self.build_despatch_lines(desp, payload)

        return desp

    # ---------------------------------------------------------
    # 1) Root oluştur
    # ---------------------------------------------------------
    def create_despatch_root(self, payload):
        """DespatchAdvice belgesi oluştur"""
        return Despatch()

    # ---------------------------------------------------------
    # 2) Header doldur
    # ---------------------------------------------------------
    def build_despatch_header(self, desp, payload):
        hdr = payload.get("Header") or {}
        lines_in = payload.get("Lines", []) or []

        desp.UBLVersionID.value = hdr.get("UBLVersionID", "2.1")
        desp.ProfileID.value = hdr.get("ProfileID", "TEMELIRSALIYE")

        desp.ID.value = hdr.get("DocNum", "") or ""
        desp.UUID.value = payload.get("UUID") or hdr.get("UUID") or ""

        desp.CopyIndicator.value = "false"

        desp.IssueDate.value = hdr.get("DocDate", "") or ""
        desp.IssueTime.value = hdr.get("IssueTime") or datetime.now().strftime("%H:%M:%S")

        desp.DespatchAdviceTypeCode.value = hdr.get("DespatchAdviceTypeCode", "SEVK")

        # Note ekle (varsa)
        for note_ref in (payload.get("Notes") or []):
            if not note_ref.get("Note"):
                continue
            n = NoteType()
            n.alg_text = str(note_ref["Note"])
            desp.Note.values.append(n)

        desp.LineCountNumeric.value = _D0(len(lines_in))

    # ---------------------------------------------------------
    # 3) DespatchSupplierParty (Sevk eden / Gönderici)
    # ---------------------------------------------------------
    def build_despatch_supplier(self, desp, payload):
        """DespatchSupplierParty - Malı gönderen/sevk eden taraf"""
        company = payload.get("Company") or payload.get("DespatchSupplier")
        if not company:
            return

        supplier = SupplierPartyType()
        party = self._build_party(company)  # Base class metodunu kullan
        supplier.Party.values.append(party)
        desp.DespatchSupplierParty.values.append(supplier)

    # ---------------------------------------------------------
    # 4) DeliveryCustomerParty (Teslim alacak müşteri)
    # ---------------------------------------------------------
    def build_delivery_customer(self, desp, payload):
        """DeliveryCustomerParty - Malı teslim alacak müşteri (ana müşteri)"""
        customer = payload.get("Customer") or payload.get("DeliveryCustomer")
        if not customer:
            return

        cust = CustomerPartyType()
        party = self._build_party(customer)  # Base class metodunu kullan
        cust.Party.values.append(party)
        desp.DeliveryCustomerParty.values.append(cust)

    # ---------------------------------------------------------
    # 5) BuyerCustomerParty (Fatura müşterisi - farklıysa)
    # ---------------------------------------------------------
    def build_buyer_customer(self, desp, payload):
        """BuyerCustomerParty - Faturayı alacak müşteri (teslim müşterisinden farklıysa)"""
        buyer_customer = payload.get("BuyerCustomer")
        if not buyer_customer:
            return

        cust = CustomerPartyType()
        party = self._build_party(buyer_customer)  # Base class metodunu kullan
        cust.Party.values.append(party)
        desp.BuyerCustomerParty.values.append(cust)

    # ---------------------------------------------------------
    # 6) SellerSupplierParty (Satıcı - gönderenden farklıysa)
    # ---------------------------------------------------------
    def build_seller_supplier(self, desp, payload):
        """SellerSupplierParty - Satıcı firma (gönderenden farklıysa)"""
        seller = payload.get("SellerSupplier")
        if not seller:
            return

        supplier = SupplierPartyType()
        party = self._build_party(seller)  # Base class metodunu kullan
        supplier.Party.values.append(party)
        desp.SellerSupplierParty.values.append(supplier)

    # ---------------------------------------------------------
    # 7) Despatch References (OrderReference, AdditionalDocumentReference)
    # ---------------------------------------------------------
    def build_despatch_references(self, desp, payload):
        """DespatchAdvice için referanslar"""
        # OrderReference (Sipariş referansları)
        for ref in (payload.get("OrderReference") or []):
            if not ref.get("OrderID"):
                continue

            order_ref = OrderReferenceType()
            order_ref.ID.value = ref["OrderID"]
            if ref.get("IssueDate"):
                order_ref.IssueDate.value = ref["IssueDate"]
            desp.OrderReference.values.append(order_ref)

        # AdditionalDocumentReference (Ek doküman referansları - irsaliye, waybill vs.)
        for ref in (payload.get("AdditionalDocumentReference") or []):
            if not ref.get("ID"):
                continue

            doc_ref = DocumentReferenceType()
            doc_ref.ID.value = ref["ID"]
            if ref.get("IssueDate"):
                doc_ref.IssueDate.value = ref["IssueDate"]
            if ref.get("DocumentTypeCode"):
                doc_ref.DocumentTypeCode.value = ref["DocumentTypeCode"]
            if ref.get("DocumentType"):
                doc_ref.DocumentType.value = ref["DocumentType"]
            desp.AdditionalDocumentReference.values.append(doc_ref)

    # ---------------------------------------------------------
    # 8) Shipment (Sevkiyat) bilgileri
    # ---------------------------------------------------------
    def build_shipment(self, desp, payload):
        """
        Shipment oluştur - UBL DespatchAdvice TR1.2 formatına uygun

        İki farklı format desteklenir:
        Format 1 (nested): {"Shipment": {"ShipmentStage": {...}, "Delivery": {...}}}
        Format 2 (flat): {"Shipment": {"VehiclePlateNumber": "...", "Drivers": [...], "TrailerPlates": [...]}}

        XSD element sırası:
        1. ID
        2. ShipmentStage (TransportMeans, DriverPerson)
        3. Delivery (DeliveryAddress, CarrierParty, Despatch, Shipment)
        4. TransportHandlingUnit (TransportEquipment)
        """
        shipment_data = payload.get("Shipment")
        if not shipment_data:
            return

        ship = ShipmentType()
        ship.ID.value = shipment_data.get("ID", "") or shipment_data.get("ShipmentID", "")

        # 1) ShipmentStage (Araç ve sürücü bilgileri)
        # Format 1: Nested ShipmentStage object
        # Format 2: Flat VehiclePlateNumber + Drivers array
        stage_data = shipment_data.get("ShipmentStage")
        vehicle_plate = shipment_data.get("VehiclePlateNumber", "").strip()
        drivers_list = shipment_data.get("Drivers") or []

        if stage_data or vehicle_plate or drivers_list:
            stage = ShipmentStageType()

            # TransportMeans (Taşıma aracı bilgileri)
            if stage_data:
                # Format 1: nested
                transport_data = stage_data.get("TransportMeans")
                if transport_data:
                    tm = TransportMeansType()
                    road_data = transport_data.get("RoadTransport")
                    if road_data:
                        road = RoadTransportType()
                        road.LicensePlateID.value = road_data.get("LicensePlateID", "")
                        road.LicensePlateID.alg_schemeID = road_data.get("SchemeID", "PLAKA")
                        tm.RoadTransport.values.append(road)
                    stage.TransportMeans.values.append(tm)
            elif vehicle_plate:
                # Format 2: flat VehiclePlateNumber
                tm = TransportMeansType()
                road = RoadTransportType()
                road.LicensePlateID.value = vehicle_plate
                road.LicensePlateID.alg_schemeID = "PLAKA"
                tm.RoadTransport.values.append(road)
                stage.TransportMeans.values.append(tm)

            # DriverPerson (Sürücü bilgileri)
            if stage_data:
                # Format 1: nested DriverPerson
                driver_data = stage_data.get("DriverPerson")
                if driver_data:
                    driver = PersonType()
                    driver.FirstName.value = driver_data.get("FirstName", "")
                    driver.FamilyName.value = driver_data.get("FamilyName", "")
                    driver.NationalityID.value = driver_data.get("NationalityID", "")
                    stage.DriverPerson.values.append(driver)
            else:
                # Format 2: flat Drivers array
                for driver_data in drivers_list:
                    driver = PersonType()
                    driver.FirstName.value = driver_data.get("Name", "") or driver_data.get("FirstName", "")
                    driver.FamilyName.value = driver_data.get("Surname", "") or driver_data.get("FamilyName", "")
                    driver.NationalityID.value = driver_data.get("TCKN", "") or driver_data.get("NationalityID", "")
                    stage.DriverPerson.values.append(driver)

            ship.ShipmentStage.values.append(stage)

        # 2) Delivery (Teslimat bilgileri)
        # Format 1: {"Delivery": {...}}
        # Format 2: Shipment içinde direkt ActualDespatchDate/Time
        delivery_data = shipment_data.get("Delivery")
        actual_despatch_date = shipment_data.get("ActualDespatchDate", "").strip()
        actual_despatch_time = shipment_data.get("ActualDespatchTime", "").strip()

        if delivery_data or actual_despatch_date:
            delivery = DeliveryType()

            # DeliveryAddress (Teslimat adresi)
            if delivery_data and delivery_data.get("DeliveryAddress"):
                addr = self._build_address(delivery_data["DeliveryAddress"])
                delivery.DeliveryAddress.values.append(addr)

            # CarrierParty (Taşıyıcı firma) - Delivery içinde!
            if delivery_data:
                carrier_data = delivery_data.get("CarrierParty")
                if carrier_data:
                    carrier_party = self._build_carrier_party(carrier_data)
                    delivery.CarrierParty.values.append(carrier_party)

            # Despatch (Sevk tarihi/saati)
            # Format 1: nested Despatch object
            # Format 2: flat ActualDespatchDate/Time
            if delivery_data and delivery_data.get("Despatch"):
                despatch_data = delivery_data["Despatch"]
                desp_elem = DespatchType()
                desp_elem.ActualDespatchDate.value = despatch_data.get("ActualDespatchDate", "")
                desp_elem.ActualDespatchTime.value = despatch_data.get("ActualDespatchTime", "") or datetime.now().strftime("%H:%M:%S")
                delivery.Despatch.values.append(desp_elem)
            elif actual_despatch_date:
                # Format 2: flat
                desp_elem = DespatchType()
                desp_elem.ActualDespatchDate.value = actual_despatch_date
                desp_elem.ActualDespatchTime.value = actual_despatch_time if actual_despatch_time else datetime.now().strftime("%H:%M:%S")
                delivery.Despatch.values.append(desp_elem)

            # Nested Shipment (Delivery içinde)
            nested_ship_data = delivery_data.get("Shipment") if delivery_data else None
            if nested_ship_data:
                nested_ship = ShipmentType()
                nested_ship.ID.value = nested_ship_data.get("ID", "")
                delivery.Shipment.values.append(nested_ship)

            ship.Delivery.values.append(delivery)

        # 3) TransportHandlingUnit (Taşıma ekipmanı - dorse plakası)
        # Format 1: {"TransportHandlingUnits": [{"TransportEquipment": {...}}]}
        # Format 2: {"TrailerPlates": ["35aaa35", "34bbb34"]}
        thu_list = shipment_data.get("TransportHandlingUnits") or []
        trailer_plates = shipment_data.get("TrailerPlates") or []

        # Format 1: nested TransportHandlingUnits
        for thu_data in thu_list:
            thu = TransportHandlingUnitType()
            equipment_data = thu_data.get("TransportEquipment")
            if equipment_data:
                equip = TransportEquipmentType()
                equip.ID.value = equipment_data.get("ID", "")
                equip.ID.alg_schemeID = equipment_data.get("SchemeID", "DORSEPLAKA")
                thu.TransportEquipment.values.append(equip)
            ship.TransportHandlingUnit.values.append(thu)

        # Format 2: flat TrailerPlates array
        for plate in trailer_plates:
            if plate and str(plate).strip():
                thu = TransportHandlingUnitType()
                equip = TransportEquipmentType()
                equip.ID.value = str(plate).strip()
                equip.ID.alg_schemeID = "DORSEPLAKA"
                thu.TransportEquipment.values.append(equip)
                ship.TransportHandlingUnit.values.append(thu)

        desp.Shipment.values.append(ship)

    def _build_carrier_party(self, carrier_data):
        """
        CarrierParty oluştur (Taşıyıcı firma)
        Base _build_party'den farklı olarak Contact ve Person bilgileri de içerir
        """
        from ...utils.ubl_tr.ubl_tr import PartyType

        party = PartyType()

        # 1) PartyIdentification
        pid_data = self._build_party_id(carrier_data)
        party.PartyIdentification.values.append(pid_data)

        # Ek PartyIdentifications
        for identification in (carrier_data.get("PartyIdentifications") or []):
            from ...utils.ubl_tr.ubl_tr import PartyIdentificationType
            add_id = PartyIdentificationType()
            add_id.ID.value = (identification.get("Value") or identification.get("ID") or "").strip()
            if identification.get("SchemeID"):
                add_id.ID.alg_schemeID = identification["SchemeID"]
            party.PartyIdentification.values.append(add_id)

        # 2) PartyName
        if carrier_data.get("Title") or carrier_data.get("Name"):
            from ...utils.ubl_tr.ubl_tr import PartyNameType
            pname = PartyNameType()
            pname.Name.value = (carrier_data.get("Title") or carrier_data.get("Name") or "").strip()
            party.PartyName.values.append(pname)

        # 3) PostalAddress
        if carrier_data.get("Address"):
            addr = self._build_address(carrier_data["Address"])
            party.PostalAddress.values.append(addr)

        # 4) PartyTaxScheme
        tax_office = carrier_data.get("TaxOffice", "").strip()
        if tax_office:
            from ...utils.ubl_tr.ubl_tr import PartyTaxSchemeType, TaxSchemeType
            pts = PartyTaxSchemeType()
            ts = TaxSchemeType()
            ts.Name.value = tax_office
            pts.TaxScheme.values.append(ts)
            party.PartyTaxScheme.values.append(pts)

        # 5) Contact (Telefon, Email)
        contact_data = carrier_data.get("Contact")
        if contact_data:
            contact = ContactType()
            if contact_data.get("Telephone"):
                contact.Telephone.value = contact_data["Telephone"]
            if contact_data.get("ElectronicMail"):
                contact.ElectronicMail.value = contact_data["ElectronicMail"]
            party.Contact.values.append(contact)

        # 6) Person (İsim soyisim)
        person_data = carrier_data.get("Person") or carrier_data.get("PersonData")
        if person_data:
            person = PersonType()
            person.FirstName.value = person_data.get("FirstName", "") or person_data.get("first_name", "")
            person.FamilyName.value = person_data.get("FamilyName", "") or person_data.get("last_name", "")
            party.Person.values.append(person)

        return party

    # ---------------------------------------------------------
    # 9) DespatchLine (İrsaliye satırları)
    # ---------------------------------------------------------
    def build_despatch_lines(self, desp, payload):
        """
        DespatchLine oluştur
        XSD element sırası (ZORUNLU):
        1. ID
        2. Note (opsiyonel)
        3. DeliveredQuantity (opsiyonel)
        4. OutstandingQuantity (opsiyonel)
        5. OutstandingReason (opsiyonel)
        6. OversupplyQuantity (opsiyonel)
        7. OrderLineReference (ZORUNLU!)
        8. DocumentReference (opsiyonel)
        9. Item (ZORUNLU!)
        10. Shipment (opsiyonel)
        """
        lines_in = payload.get("Lines", []) or []

        for idx, line_data in enumerate(lines_in, start=1):
            dline = DespatchLineType()

            # 1) ID
            dline.ID.value = str(line_data.get("LineNum", idx))

            # 2) Note (opsiyonel - şimdilik kullanmıyoruz)

            # 3) DeliveredQuantity
            delivered_qty = _to_dec(line_data.get("DeliveredQuantity", line_data.get("Quantity", 0)))
            dline.DeliveredQuantity.value = _D2(delivered_qty)
            dline.DeliveredQuantity.alg_unitCode = line_data.get("UnitCode", "C62")

            # 4) OutstandingQuantity (opsiyonel)
            if line_data.get("OutstandingQuantity"):
                outstanding = _to_dec(line_data["OutstandingQuantity"])
                dline.OutstandingQuantity.value = _D2(outstanding)
                dline.OutstandingQuantity.alg_unitCode = line_data.get("UnitCode", "C62")

            # 5) OutstandingReason (opsiyonel - şimdilik kullanmıyoruz)

            # 6) OversupplyQuantity (opsiyonel)
            if line_data.get("OversupplyQuantity"):
                oversupply = _to_dec(line_data["OversupplyQuantity"])
                dline.OversupplyQuantity.value = _D2(oversupply)
                dline.OversupplyQuantity.alg_unitCode = line_data.get("UnitCode", "C62")

            # 7) OrderLineReference (ZORUNLU - XSD'de required!)
            # Eğer yoksa default bir değer ekliyoruz
            olr = OrderLineReferenceType()
            olr.LineID.value = str(line_data.get("OrderLineReference", idx))
            dline.OrderLineReference.values.append(olr)

            # 8) DocumentReference (opsiyonel - şimdilik kullanmıyoruz)

            # 9) Item (ZORUNLU!)
            item = self.build_despatch_item(line_data)
            dline.Item.values.append(item)

            # 10) Shipment (opsiyonel - satır düzeyinde şimdilik kullanmıyoruz)

            desp.DespatchLine.values.append(dline)

    def build_despatch_item(self, line_data):
        """
        İrsaliye satırı için Item oluştur
        XSD element sırası (ZORUNLU):
        1. Description (opsiyonel)
        2. Name (ZORUNLU!)
        3. Keyword, BrandName, ModelName (opsiyonel)
        4. BuyersItemIdentification (opsiyonel)
        5. SellersItemIdentification (opsiyonel)
        6. ManufacturersItemIdentification (opsiyonel)
        7. AdditionalItemIdentification (opsiyonel) - GTIN için kullanılır
        """
        item = ItemType()

        # 1) Description (opsiyonel)
        if line_data.get("ItemDescription"):
            item.Description.value = line_data["ItemDescription"]

        # 2) Name (ZORUNLU!)
        item.Name.value = line_data.get("ItemName", "")

        # 3-4) Keyword, BrandName, ModelName, BuyersItemIdentification (şimdilik kullanmıyoruz)

        # 5) SellersItemIdentification - Satıcı ürün kodu
        if line_data.get("ItemCode"):
            seller_id = ItemIdentificationType()
            seller_id.ID.value = line_data["ItemCode"]
            seller_id.ID.alg_schemeID = "SELLER"
            item.SellersItemIdentification.values.append(seller_id)

        # 6) ManufacturersItemIdentification (şimdilik kullanmıyoruz)

        # 7) AdditionalItemIdentification - GTIN / Barkod
        if line_data.get("GTIN"):
            gtin_id = ItemIdentificationType()
            gtin_id.ID.value = line_data["GTIN"]
            gtin_id.ID.alg_schemeID = "GTIN"
            item.AdditionalItemIdentification.values.append(gtin_id)

        return item

    # Not: _build_party ve _build_address metodları UBLBaseBuilder'dan miras alınıyor


# -------------------------------------------------------
# ODOO MODEL WRAPPER
# -------------------------------------------------------
class AlgebraUBLDespatch(models.AbstractModel):
    _name = "algebra.ubl.despatch"
    _description = "UBL DespatchAdvice Builder Wrapper"
    _builder_class = DespatchBuilder
