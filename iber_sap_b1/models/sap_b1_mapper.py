# -*- coding: utf-8 -*-
"""
SAP Business One Field Mapper
------------------------------
Maps SAP B1 fields (OINV/INV1/ODLN/DLN1) to Odoo UBL fields.
Based on SAP B1 UDF structure defined in adevdocs folder.
"""

from datetime import datetime
from dateutil.parser import parse
from odoo.addons.iber_e_transform.models.erp.erp_mapper_base import ERPMapperBase
from typing import Dict, Any
import logging

_logger = logging.getLogger(__name__)


class SAPB1Mapper(ERPMapperBase):
    """SAP Business One to Odoo UBL field mapper."""

    def get_erp_system_name(self) -> str:
        return "SAP_B1"

    def get_invoice_object_type(self) -> str:
        return "OINV"

    def get_delivery_note_object_type(self) -> str:
        return "ODLN"

    def parse_datetime_combined(self, date_str: str, time_str: str):
        """
        Combine date and time strings into a single datetime object.

        Args:
            date_str: Date string (e.g., '2024-01-31')
            time_str: Time string (e.g., '14:30:00')
        Returns:
            Combined datetime object or None
        """
        if not date_str:
            return None
        try:
            date_part = self.parse_date(date_str)
            if time_str:
                time_part = parse(time_str).time()
                combined_dt = datetime.combine(date_part, time_part)
                return combined_dt
            return date_part
        except Exception as e:
            _logger.error(f"Error parsing combined datetime from '{date_str}' and '{time_str}': {e}")
            return None
    # ========================================
    # INVOICE HEADER MAPPING (OINV -> l10n_tr.ubl.invoice)
    # ========================================
    def map_invoice_header(self, erp_data: Dict[str, Any], connector=None) -> Dict[str, Any]:
        """
        Map SAP B1 OINV (Invoice Header) to Odoo invoice fields.

        SAP B1 OINV Structure (from adevdocs/sap_fatura_udf.txt):
        - DocEntry, DocNum: SAP document identifiers
        - U_UUID: E-Invoice UUID
        - U_InvoiceSeriesNum, U_InvoiceEnvelopeNum: Series/Envelope numbers
        - U_InvoiceType, U_InvoiceProfile, U_SendInvoiceType
        - U_InvoiceStatus, U_ERPStatus: Status fields
        - CardCode, CardName: Customer code/name
        - DocCurrency: Currency
        - DocRate: Exchange Rate
        - DocDate, DocDueDate, TaxDate: Dates
        - DocTotal, VatSum: Totals
        - Comments: Notes
        - U_PaymentTerms : PaymentTermsNote
        - U_PayeeCode : PaymentMeansCode
        - U_PayeeChannelCode : PaymentChannelCode
        - U_PayeeDueDate : PaymentDueDate
        - U_PayeeFinAccountID : PayeeFinancialAccount
        - U_PayeeNote : InstructionNote
        - U_PayeeVKN : Payee VKN
        - U_PayeeName : Payee Name
        - U_OKCID : okc_fis_no
        - U_OKCIssueDate , U_OKCTime : okc_fis_tarih_saat
        - U_OKCZNo : okc_z_rapor_no
        - U_OKCEndPointID : okc_seri_no
        - U_OKCDocDescription : okc_fis_tipi
        - U_SGKInvoiceType : sgk_invoice_type
        - U_SGKMukellefKod : sgk_company_code
        - U_SGKMukellefAdi : sgk_company_name
        - U_SGKDosyaNo : sgk_file_number
        - U_GTIPNo : gtip_num
        - U_DeliveryTermCode : incoterm_code
        - U_TransportModeCode : transport_type
        - U_PackageBrandName : package_brand_name?
        - U_ProductTraceID : product_traceID
        - U_PackageID : container_number
        - U_PackageQuantity : container_count
        - U_PackageTypeCode : container_type
        - DocumentLines : Invoice Lines
        - WithholdingTaxDataCollection : Withholding Taxes
        - AddressExtension : Address Info


        Args:
            erp_data: SAP invoice data
            connector: SAPB1Connector instance for fetching BusinessPartner (optional)
        """
        # Get settings for supplier info
        settings = self.env["ubl21.config.settings"].get_singleton()

        # Fetch customer VKN from BusinessPartners if connector provided
        customer_vkn = None
        card_code = erp_data.get('CardCode')
        if connector and card_code:
            bp_data = connector.fetch_business_partner(card_code)
            if bp_data:
                # UnifiedFederalTaxID contains VKN/TCKN
                customer_vkn = self.safe_str(bp_data.get('UnifiedFederalTaxID'))

        # Map BPLId (Branch) from SAP to Odoo
        branch_id = self._map_branch_id(erp_data.get('BPL_IDAssignedToInvoice'))
        address_extension = erp_data.get('AddressExtension', {})
        odoo_vals = {
            # === ERP Tracking ===
            'erp_id': str(erp_data.get('DocEntry', '')),
            'erp_object_type': self.get_invoice_object_type(),
            'branch_id': branch_id,

            # === UBL Header Fields ===
            'UUID': self.safe_str(erp_data.get('U_UUID')),
            'id_value': self.safe_str(erp_data.get('U_InvoiceSeriesNum')) or self.safe_str(erp_data.get('DocEntry')),
            'issue_date': self.parse_date(erp_data.get('DocDate')),



            # === Currency ===
            'document_currency_id': self.get_or_create_currency(erp_data.get('DocCurrency', 'TRY')).id,
            'document_exchange_rate': self.safe_float(erp_data.get('DocRate'), 1.0),
            # === Notes ===
            'note': self.safe_str(erp_data.get('Comments')),
            'customer_card_code': card_code or '',
            'customer_receiver_alias': self.safe_str(erp_data.get('U_ReceiverAlias')),
            # === Customer Party ===
            'customer_name': self.safe_str(erp_data.get('CardName')),
            'customer_vkn_tckn': customer_vkn or '',
            'customer_scheme_id': self._determine_scheme_id(customer_vkn) if customer_vkn else 'VKN',
            'customer_street': self.safe_str(address_extension.get('Street')),
            'customer_county': self.safe_str(address_extension.get('County')),
            'customer_city': self.safe_str(address_extension.get('City')),
            'customer_postal_code': self.safe_str(address_extension.get('PostalCode')),
            'customer_country_code': self.safe_str(address_extension.get('CountryCode')) or 'TR',
            'customer_country_name': self.safe_str(address_extension.get('CountryName')) or 'TÜRKİYE',
            # === Supplier Party (from Odoo settings) ===
            'supplier_name': settings.erp_company_name if settings else '',
            'supplier_vkn_tckn': settings.erp_vkn_tckn if settings else '',
            'supplier_tax_office': settings.erp_tax_office if settings else '',
            'supplier_scheme_id': self._determine_scheme_id(settings.erp_vkn_tckn) if settings and settings.erp_vkn_tckn else 'VKN',
            'supplier_street': settings.erp_street if settings else '',
            'supplier_county': settings.erp_county if settings else '',
            'supplier_city': settings.erp_city if settings else '',
            'supplier_postal_code': settings.erp_postal_code if settings else '',
            'supplier_country_code': settings.erp_country_code if settings else 'TR',
            'supplier_country_name': settings.erp_country_name if settings else 'TÜRKİYE',
            # === Payment Terms ===
            'PaymentTermsNote': self.safe_str(erp_data.get('U_PaymentTerms')),
            'PaymentMeansCode': self.safe_str(erp_data.get('U_PayeeCode')),
            'PaymentChannelCode': self.safe_str(erp_data.get('U_PayeeChannelCode')),
            'PaymentDueDate':  self.parse_date(erp_data.get('U_PayeeDueDate')),
            'PayeeFinancialAccount': self.safe_str(erp_data.get('U_PayeeFinAccountID')),
            'InstructionNote': self.safe_str(erp_data.get('U_PayeeNote')),
            # 'payee_vkn': self.safe_str(erp_data.get('U_PayeeVKN')),
            # 'payee_name': self.safe_str(erp_data.get('U_PayeeName')),
            # === OKC Fields ===
            'okc_fis_no': self.safe_str(erp_data.get('U_OKCID')),
            'okc_seri_no': self.safe_str(erp_data.get('U_OKCEndPointID')),
            'okc_fis_tarih_saat': self.parse_datetime_combined(
                erp_data.get('U_OKCIssueDate'),
                erp_data.get('U_OKCTime')
            ),
            'okc_z_rapor_no': self.safe_str(erp_data.get('U_OKCZNo')),
            'okc_fis_tipi': self.safe_str(erp_data.get('U_OKCDocDescription')),
            # === SGK Fields ===
            'sgk_invoice_type': self.safe_str(erp_data.get('U_SGKInvoiceType')),
            'sgk_company_code': self.safe_str(erp_data.get('U_SGKMukellefKod')),
            'sgk_company_name': self.safe_str(erp_data.get('U_SGKMukellefAdi')),
            'sgk_file_number': self.safe_str(erp_data.get('U_SGKDosyaNo')),
        }

        # Invoice Type - Map SAP numeric code to Odoo string code
        sap_invoice_type = self.safe_str(erp_data.get('U_SendInvoiceType', '0'))
        invoice_type_code = self._map_invoice_type(sap_invoice_type)
        invoice_type = self.get_or_create_invoice_type(
            invoice_type_code,
            invoice_type_code
        )
        if invoice_type:
            odoo_vals['document_type_id'] = invoice_type.id
        base_type_code = self.safe_str(erp_data.get('U_InvoiceType', '0'))
        profile_id_code = self._map_profile_id(erp_data.get('U_InvoiceProfile')) if base_type_code != "1" else "EARSIVFATURA"
        profile_id = self.get_or_create_profile_id(
            profile_id_code,
            profile_id_code
        )
        if profile_id:
            odoo_vals['profile_id'] = profile_id.id

        return odoo_vals

    # ========================================
    # INVOICE LINE MAPPING (INV1 -> l10n_tr.ubl.invoiceline)
    # ========================================
    def map_invoice_line(self,doctype, erp_line_data: Dict[str, Any], line_num: int, connector=None) -> Dict[str, Any]:
        """
        Map SAP B1 INV1 (Invoice Line) to Odoo invoice line fields.

        SAP B1 INV1 Structure (from adevdocs/sap_fatura_kalem_udf.txt):
        - LineNum: Line number
        - ItemCode, Dscription: Item code and description
        - Quantity, Price, LineTotal: Quantities and amounts
        - VatPrcnt, VatSum: Tax percentage and amount
        - UoMCode: SAP Unit of Measure Code
        - U_EDocItemCode, U_EDocItemName, U_EDocItemDesc, U_EDocItemNote
        - U_BuyerCode, U_ManufacturerCode
        - U_ReasonCode: Withholding tax code
        - U_DiscPrcnt1, U_DiscPrcnt2, U_DiscPrcnt3
        - U_GTIN, U_YerlilikOrani

        - U_GTIPNo : gtip_num
        - U_DeliveryTermCode : incoterm_code
        - U_TransportModeCode : transport_type
        - U_PackageBrandName : package_brand_name?
        - U_ProductTraceID : product_traceID
        - U_PackageID : container_number
        - U_PackageQuantity : container_count
        - U_PackageTypeCode : container_type

        

        Args:
            erp_line_data: SAP invoice line data
            line_num: Line sequence number
            connector: SAPB1Connector instance for unit mapping (optional)
        """
        odoo_vals = {
            #'sequence': line_num,

            # === Item Info ===
            #'item_code': self.safe_str(erp_line_data.get('U_EDocItemCode')) or self.safe_str(erp_line_data.get('ItemCode')),
            'name': self.safe_str(erp_line_data.get('U_EDocItemName')) or self.safe_str(erp_line_data.get('ItemDescription')),
            'description': self.safe_str(erp_line_data.get('U_EDocItemDesc')) or self.safe_str(erp_line_data.get('ItemDescription')),

            # === Quantities and Prices ===
            'quantity': self.safe_float(erp_line_data.get('U_EDocItemQty')) > 0 if self.safe_float(erp_line_data.get('U_EDocItemQty')) > 0 else (self.safe_float(erp_line_data.get('Quantity')) if self.safe_float(erp_line_data.get('Quantity')) > 0 else 1.0), 
            'price_amount': self.safe_float(erp_line_data.get('UnitPrice'), 0.0),
            'currency_id': self.get_or_create_currency(erp_line_data.get('Currency', 'TRY')).id,
            'line_extension_amount': self.safe_float(erp_line_data.get('LineTotal'), 0.0),

            # === Tax Info ===
            'tax_percent': self.safe_float(erp_line_data.get('TaxPercentagePerRow'), 0.0),
            'tax_amount': self.safe_float(erp_line_data.get('TaxTotal'), 0.0),

            # === Buyer/Manufacturer Codes ===
            # U_BuyerCode, U_ManufacturerCode - can be stored in notes or custom fields

            # === Export Fields ===
            # U_GTIPNo, U_DeliveryTermCode, U_TransportModeCode, U_PackageBrandName, etc.
            # These would need corresponding fields in Odoo invoice line model
            'gtip_num': self.safe_str(erp_line_data.get('U_GTIPNo')),
            'incoterm_code': self.safe_str(erp_line_data.get('U_DeliveryTermCode')),
            'transport_type': self.safe_str(erp_line_data.get('U_TransportModeCode')),
            #'package_brand_name': self.safe_str(erp_line_data.get('U_PackageBrandName')),
            'product_traceID': self.safe_str(erp_line_data.get('U_ProductTraceID')),
            'container_number': self.safe_str(erp_line_data.get('U_PackageID')),
            'container_count': self.safe_float(erp_line_data.get('U_PackageQuantity')),
            'container_type': self.safe_str(erp_line_data.get('U_PackageTypeCode')),

            # === Withholding Tax ===
            # U_ReasonCode - tevkifat kodu

            # === Discounts ===
            # U_DiscPrcnt1, U_DiscPrcnt2, U_DiscPrcnt3

            # === Other ===
            # U_GTIN, U_YerlilikOrani
        }

        # === Unit Code Mapping ===
        # Map SAP UoMCode to UBL unit code using connector's cached mappings
        if doctype == 'dDocument_Items':
            sap_uom_code = erp_line_data.get('UoMCode')
            if sap_uom_code and connector:
                ubl_unit_code = connector.get_ubl_unit_code(sap_uom_code)
                  
        else:
            ubl_unit_code = "C62"
        if ubl_unit_code:
            # Get unit record from database
            unit_record = self.get_or_create_unit(ubl_unit_code)
            
        if unit_record:
            odoo_vals['unit_code_id'] = unit_record.id
        line_adj_commands = []
        discount = self.safe_float(erp_line_data.get('DiscountPercent'), 0.0)
        if discount > 0.0:
            # Apply discount to price_amount
            discount_row = {
                'type': 'discount',
                'rate': discount,
            }
            line_adj_commands.append((0, 0, discount_row))

        if line_adj_commands:
            odoo_vals['adjustment_ids'] = line_adj_commands
        # Add note if available
        # if erp_line_data.get('U_EDocItemNote'):
        #     odoo_vals['note'] = self.safe_str(erp_line_data.get('U_EDocItemNote'))

        return odoo_vals

    # ========================================
    # DELIVERY NOTE HEADER MAPPING (ODLN -> l10n_tr.ubl.delivery.note)
    # ========================================
    def map_delivery_note_header(self, erp_data: Dict[str, Any], connector=None) -> Dict[str, Any]:
        """
        Map SAP B1 ODLN (Delivery Note Header) to Odoo delivery note fields.

        Note: SAP B1 uses the same UDF structure for delivery notes as invoices.
        ODLN has similar fields to OINV.

        Args:
            erp_data: SAP delivery note data
            connector: SAPB1Connector instance for fetching BusinessPartner (optional)
        """
        # Get settings for supplier info
        settings = self.env["ubl21.config.settings"].get_singleton()

        # Fetch customer VKN from BusinessPartners if connector provided
        customer_vkn = None
        card_code = erp_data.get('CardCode')
        if connector and card_code:
            bp_data = connector.fetch_business_partner(card_code)
            if bp_data:
                customer_vkn = self.safe_str(bp_data.get('UnifiedFederalTaxID'))

        # Map BPLId (Branch) from SAP to Odoo
        branch_id = self._map_branch_id(erp_data.get('BPL_IDAssignedToInvoice'))

        odoo_vals = {
            # === ERP Tracking ===
            'erp_id': str(erp_data.get('DocEntry', '')),
            'erp_object_type': self.get_delivery_note_object_type(),
            'branch_id': branch_id,

            # === UBL Header Fields ===
            'UUID': self.safe_str(erp_data.get('U_UUID')),
            'id_value': self.safe_str(erp_data.get('U_InvoiceSeriesNum')) or self.safe_str(erp_data.get('DocEntry')),
            'issue_date': self.parse_date(erp_data.get('DocDate')),


            # === Customer Party ===
            'customer_name': self.safe_str(erp_data.get('CardName')),
            'customer_vkn_tckn': customer_vkn or '',
            'customer_scheme_id': self._determine_scheme_id(customer_vkn) if customer_vkn else 'VKN',


            # === Supplier Party (from Odoo settings) ===
            'supplier_name': settings.erp_company_name if settings else '',
            'supplier_vkn_tckn': settings.erp_vkn_tckn if settings else '',
            'supplier_scheme_id': self._determine_scheme_id(settings.erp_vkn_tckn) if settings and settings.erp_vkn_tckn else 'VKN',

            # === Notes ===
            'note': self.safe_str(erp_data.get('Comments')),
        }
        #TODO DocumentTypeID mapping for delivery notes

        profile_id_code = self._map_delivery_profile_id(erp_data.get('U_InvoiceProfile'))
        profile_id = self.get_or_create_profile_id(
            profile_id_code,
            profile_id_code
        )
        if profile_id:
            odoo_vals['profile_id'] = profile_id.id
        return odoo_vals

    # ========================================
    # DELIVERY NOTE LINE MAPPING (DLN1 -> l10n_tr.ubl.delivery.note.line)
    # ========================================
    def map_delivery_note_line(self, erp_line_data: Dict[str, Any], line_num: int, connector=None) -> Dict[str, Any]:
        """
        Map SAP B1 DLN1 (Delivery Note Line) to Odoo delivery note line fields.

        Note: DLN1 uses same UDF structure as INV1.
        """
        odoo_vals = {
            'sequence': line_num,

            # === Item Info ===
            'item_code': self.safe_str(erp_line_data.get('U_EDocItemCode')) or self.safe_str(erp_line_data.get('ItemCode')),
            'item_name': self.safe_str(erp_line_data.get('U_EDocItemName')) or self.safe_str(erp_line_data.get('Dscription')),
            'description': self.safe_str(erp_line_data.get('U_EDocItemDesc')) or self.safe_str(erp_line_data.get('Dscription')),

            # === Quantities ===
            'quantity': self.safe_float(erp_line_data.get('U_EDocItemQty')) or self.safe_float(erp_line_data.get('Quantity'), 1.0),

            # === Note ===
            'note': self.safe_str(erp_line_data.get('U_EDocItemNote')),
        }

        return odoo_vals

    # ========================================
    # HELPER METHODS
    # ========================================

    def _map_branch_id(self, sap_bpl_id):
        """
        Map SAP BPL_IDAssignedToInvoice to Odoo branch_id.

        Args:
            sap_bpl_id: SAP Business Place ID (numeric or string)

        Returns:
            Odoo branch ID or None
        """
        if not sap_bpl_id:
            return None

        # Convert to string
        bpl_id_str = str(sap_bpl_id)

        # Find ERP mapping
        mapping = self.env['algebra.base.branch.erp.mapping'].search([
            ('erp_system', '=', 'SAP_B1'),
            ('erp_branch_id', '=', bpl_id_str)
        ], limit=1)

        if mapping and mapping.branch_id:
            return mapping.branch_id.id

        _logger.warning(f"No branch mapping found for SAP BPLId: {sap_bpl_id}")
        return None

    def _map_profile_id(self, sap_profile: str) -> str:
        """
        Map SAP U_InvoiceProfile (numeric code) to Odoo profile_id (string code).

        SAP B1 U_InvoiceProfile Mapping:
        "0" -> TEMELFATURA
        "1" -> TICARIFATURA
        "2" -> IHRACAT
        "3" -> YOLCUBERABERFATURA
        "4" -> EARSIVFATURA
        "5" -> KAMU
        "6" -> HKS
        "7" -> EARSIVBELGE
        "8" -> ENERJI
        "9" -> ILAC_TIBBICIHAZ
        """
        if not sap_profile:
            return None

        # SAP B1 numeric to Odoo string mapping
        profile_mapping = {
            "0": "TEMELFATURA",
            "1": "TICARIFATURA",
            "2": "IHRACAT",
            "3": "YOLCUBERABERFATURA",
            "4": "EARSIVFATURA",
            "5": "KAMU",
            "6": "HKS",
            "7": "EARSIVBELGE",
            "8": "ENERJI",
            "9": "ILAC_TIBBICIHAZ",
        }

        # If numeric code, map it
        if sap_profile in profile_mapping:
            return profile_mapping[sap_profile]

        # If already string code, return as-is
        valid_profiles = [
            "TEMELFATURA", "TICARIFATURA", "IHRACAT",
            "YOLCUBERABERFATURA", "EARSIVFATURA", "KAMU",
            "HKS", "EARSIVBELGE", "ENERJI", "ILAC_TIBBICIHAZ"
        ]
        if sap_profile in valid_profiles:
            return sap_profile

        # Default fallback
        _logger.warning(f"Unknown SAP profile: {sap_profile}, using EARSIVFATURA")
        return "EARSIVFATURA"

    def _map_invoice_type(self, sap_invoice_type: str) -> str:
        """
        Map SAP U_InvoiceType (numeric code) to Odoo invoice_type_code (string code).

        SAP B1 U_InvoiceType (Fatura_Tipi) Mapping:
        "0" -> SATIS
        "1" -> IADE
        "2" -> ISTISNA
        "3" -> TEVKIFAT
        "4" -> IHRACKAYITLI
        "5" -> TEVKIFATIIADE
        "6" -> SGK
        "7" -> OZELMATRAH
        "8" -> SARJANLIK
        "9" -> SARJ
        """
        if not sap_invoice_type:
            return None

        # SAP B1 numeric to Odoo string mapping
        invoice_type_mapping = {
            "0": "SATIS",
            "1": "IADE",
            "2": "ISTISNA",
            "3": "TEVKIFAT",
            "4": "IHRACKAYITLI",
            "5": "TEVKIFATIIADE",
            "6": "SGK",
            "7": "OZELMATRAH",
            "8": "SARJANLIK",
            "9": "SARJ",
        }

        # If numeric code, map it
        if sap_invoice_type in invoice_type_mapping:
            return invoice_type_mapping[sap_invoice_type]

        # If already string code, return as-is
        valid_types = [
            "SATIS", "IADE", "ISTISNA", "TEVKIFAT",
            "IHRACKAYITLI", "TEVKIFATIIADE", "SGK",
            "OZELMATRAH", "SARJANLIK", "SARJ"
        ]
        if sap_invoice_type in valid_types:
            return sap_invoice_type

        # Default fallback
        _logger.warning(f"Unknown SAP invoice type: {sap_invoice_type}, using SATIS")
        return "SATIS"

    def _map_delivery_profile_id(self, sap_profile: str) -> str:
        """Map SAP delivery note profile."""
        # Delivery notes typically use TEMELIRSALIYE
        return "TEMELIRSALIYE"


    def _determine_scheme_id(self, vkn_tckn: str) -> str:
        """
        Determine if ID is VKN (10 digits) or TCKN (11 digits).

        Args:
            vkn_tckn: VKN or TCKN number

        Returns:
            'VKN' or 'TCKN'
        """
        if not vkn_tckn:
            return "VKN"

        # Remove non-numeric characters
        numeric_only = ''.join(filter(str.isdigit, str(vkn_tckn)))

        if len(numeric_only) == 11:
            return "TCKN"
        elif len(numeric_only) == 10:
            return "VKN"

        return "VKN"  # Default
