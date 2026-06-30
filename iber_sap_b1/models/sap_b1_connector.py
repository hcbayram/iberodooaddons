# -*- coding: utf-8 -*-
"""
SAP Business One Service Layer Connector
-----------------------------------------
Handles authentication and data retrieval from SAP B1 Service Layer.
"""

import requests
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SAPB1Connector:
    """
    SAP Business One Service Layer API connector.

    Handles:
    - Login/authentication with session management
    - Fetching invoices (OINV) with filters
    - Fetching delivery notes (ODLN) with filters
    - Logout
    """

    def __init__(self, settings, env=None):
        """
        Initialize SAP B1 connector with settings.

        Args:
            settings: ubl21.config.settings recordset
            env: Odoo environment (for accessing models)
        """
        self.service_url = settings.sap_service_layer_url
        self.company_db = settings.sap_company_db
        self.username = settings.sap_username
        self.password = settings.sap_password
        self.env = env  # Odoo environment for model access

        # Session management
        self.session = None
        self.session_id = None
        self.session_timeout = None

        # Validate settings
        if not all([self.service_url, self.company_db, self.username, self.password]):
            raise ValueError("SAP B1 connection settings are incomplete!")

        # Normalize URL
        if not self.service_url.endswith('/'):
            self.service_url += '/'

    def login(self) -> bool:
        """
        Authenticate with SAP B1 Service Layer.

        Returns:
            True if login successful, False otherwise

        Raises:
            UserError: When connection fails due to network issues
        """
        try:
            login_url = f"{self.service_url}Login"
            login_data = {
                "CompanyDB": self.company_db,
                "UserName": self.username,
                "Password": self.password
            }

            _logger.info(f"Attempting SAP B1 login to {login_url}")

            self.session = requests.Session()
            response = self.session.post(
                login_url,
                json=login_data,
                headers={"Content-Type": "application/json"},
                timeout=30,
                verify=False  # SSL verification - set to True in production
            )

            if response.status_code == 200:
                result = response.json()
                self.session_id = result.get("SessionId")
                self.session_timeout = result.get("SessionTimeout")
                _logger.info(f"SAP B1 login successful. SessionId: {self.session_id}")
                return True
            else:
                _logger.error(f"SAP B1 login failed. Status: {response.status_code}, Response: {response.text}")
                return False

        except requests.exceptions.ConnectionError as e:
            error_msg = f"SAP B1'e bağlanılamıyor. Lütfen ağ bağlantınızı ve SAP sunucusunun erişilebilir olduğunu kontrol edin.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.Timeout as e:
            error_msg = f"SAP B1 bağlantı zaman aşımı. Sunucu yanıt vermiyor.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"SAP B1 bağlantı hatası oluştu.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except Exception as e:
            _logger.error(f"SAP B1 login exception: {str(e)}")
            return False

    def logout(self):
        """Logout from SAP B1 Service Layer."""
        if not self.session:
            return

        try:
            logout_url = f"{self.service_url}Logout"
            self.session.post(logout_url, timeout=10)
            _logger.info("SAP B1 logout successful")
        except Exception as e:
            _logger.warning(f"SAP B1 logout exception: {str(e)}")
        finally:
            self.session = None
            self.session_id = None

    def fetch_invoices(self, erp_status: str = "0", bpl_id: Optional[str] = None, last_sync_datetime=None) -> List[Dict[str, Any]]:
        """
        Fetch invoices from SAP B1 filtered by ERPStatus and optionally by BPLId (Branch).

        ERPStatus Values:
        - '0': Gönderilecek (To be sent) - DEFAULT
        - '1': Gönderildi (Sent)
        - '2': İletildi - Cevap Bekleniyor (Delivered - Waiting for response)
        - '3': Onaylandı (Approved)
        - '4': Reddedildi (Rejected)
        - '5': Hatalı (Error)
        - '6': Tamamlandı (Completed)

        Args:
            erp_status: Value for U_ERPStatus filter (default: "0" for documents to send)
            bpl_id: SAP Business Place ID for branch filtering (optional)
            last_sync_datetime: Last successful sync datetime (fetches documents updated after this time)

        Returns:
            List of invoice dictionaries

        A.U_PaymentTerms AS 'Ödeme Koşulu',
		A.U_PayeeCode AS 'Ödeme Şekli Kodu',
		A.U_PayeeChannelCode AS 'Ödeme Kanalı Kodu',
		FORMAT(A.U_PayeeDueDate, N'd', N'en-US')  AS 'Son Ödeme Günü',
		--A.U_PayeeDueDate AS 'Son Ödeme Günü',
		A.U_PayeeFinAccountID AS 'Ödeme Yapılacak Hesap',
		A.U_PayeeNote AS 'Ödeme Şekli Notu',
		A."U_PayeeVKN" AS 'Harcama Birimi VKN',
		A."U_PayeeName" AS 'Harcama Birimi Ünvan',

        A.U_OKCID,
		A.U_OKCIssueDate,
		A.U_OKCTime,
		A.U_OKCZNo,
		A.U_OKCEndPointID,
		A.U_OKCDocDescription,

        A.U_SGKInvoiceType,
		A.U_SGKMukellefKod,
		A.U_SGKMukellefAdi,
		A.U_SGKDosyaNo,
        """
        if not self.session:
            if not self.login():
                raise ConnectionError("Failed to login to SAP B1")

        try:
            # Select fields (including UDFs and collections)
            # NOTE: DocumentLines and WithholdingTaxDataCollection are included in select, NOT expand
            select_fields = (
                "DocObjectCode,U_ERPStatus,U_InvoiceStatus,DocEntry,DocNum,"
                "CardCode,CardName,DocumentStatus,DocType,DocDate,DocDueDate,"
                "DocTotal,DocCurrency,DocRate,VatSum,Cancelled,Comments,BPL_IDAssignedToInvoice,"
                "U_UUID,U_InvoiceSeriesNum,U_InvoiceEnvelopeNum,"
                "U_InvoiceType,U_InvoiceProfile,U_SendInvoiceType,"
                "U_PaymentTerms,U_PayeeCode,U_PayeeChannelCode,U_PayeeDueDate,U_PayeeFinAccountID,U_PayeeNote,U_PayeeVKN,U_PayeeName,"
                "U_OKCID,U_OKCIssueDate,U_OKCTime,U_OKCZNo,U_OKCEndPointID,U_OKCDocDescription,"
                "U_SGKInvoiceType,U_SGKMukellefKod,U_SGKMukellefAdi,U_SGKDosyaNo,"
                "U_GTIPNo,U_DeliveryTermCode,U_TransportModeCode,U_PackageBrandName,U_ProductTraceID,U_PackageID,U_PackageQuantity,U_PackageTypeCode,"
                "UpdateDate,"
                "DocumentLines,WithholdingTaxDataCollection,AddressExtension"
            )
            select_query = f"$select={select_fields}"

            # Build OData filter (based on provided query pattern)
            filter_conditions = [
                #"DocumentStatus ne 'bost_Close'",
                "U_ISArchived ne 'Y'",
                "Cancelled eq 'tNO'",
                f"U_ERPStatus eq '{erp_status}'",
                "U_ERPStatus ne ''",
                "U_ERPStatus ne '-'",
                "U_ERPStatus ne null"
            ]

            # Add branch filter if specified
            if bpl_id:
                filter_conditions.append(f"BPL_IDAssignedToInvoice eq {bpl_id}")

            # Add UpdateDate filter if last_sync_datetime provided
            if last_sync_datetime:
                # Format datetime to SAP OData format: yyyy-MM-ddTHH:mm:ss
                sync_date_str = last_sync_datetime.strftime('%Y-%m-%dT%H:%M:%S')
                filter_conditions.append(f"UpdateDate ge '{sync_date_str}'")
                _logger.info(f"Filtering invoices updated after: {sync_date_str}")

            filter_query = f"$filter={' and '.join(filter_conditions)}"

            # Combine queries (NO EXPAND - causes errors in SAP Service Layer)
            query_string = f"{select_query}&{filter_query}"

            invoices_url = f"{self.service_url}Invoices?{query_string}"
            purchase_credit_notes_url = f"{self.service_url}PurchaseCreditNotes?{query_string}"
            query_string = f"{query_string} and DocumentStatus ne 'bost_Close'"
            drafts_url = f"{self.service_url}Drafts?{query_string}"
            drafts_payload = {
                "ObjectType": "13" # Filter drafts to only invoices        
            }

            _logger.info(f"Fetching SAP B1 invoices with ERPStatus={erp_status}")

            response = self.session.get(invoices_url, timeout=60)

            if response.status_code == 200:
                result = response.json()
                invoices = result.get("value", [])

                _logger.info(f"Fetched {len(invoices)} invoices from SAP B1")


            response = self.session.get(drafts_url, data=drafts_payload, timeout=60)

            if response.status_code == 200:
                result = response.json()
                invoices.extend(result.get("value", []))
            _logger.info(f"Total invoices after including drafts: {len(invoices)}")
            response = self.session.get(purchase_credit_notes_url, timeout=60)
            if response.status_code == 200:
                result = response.json()
                invoices.extend(result.get("value", []))
            _logger.info(f"Total invoices after including drafts and credit notes: {len(invoices)}")
            return invoices

        except requests.exceptions.ConnectionError as e:
            error_msg = f"SAP B1'den fatura çekilirken bağlantı hatası oluştu. Lütfen ağ bağlantınızı kontrol edin.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.Timeout as e:
            error_msg = f"SAP B1'den fatura çekilirken zaman aşımı oluştu. Sunucu yanıt vermiyor.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"SAP B1'den fatura çekilirken hata oluştu.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except Exception as e:
            _logger.error(f"Exception while fetching invoices: {str(e)}")
            return []

    def fetch_delivery_notes(self, erp_status: str = "0", bpl_id: Optional[str] = None, last_sync_datetime=None) -> List[Dict[str, Any]]:
        """
        Fetch delivery notes from SAP B1 filtered by ERPStatus and optionally by BPLId (Branch).

        ERPStatus Values: Same as invoices (0-6)

        Args:
            erp_status: Value for U_ERPStatus filter (default: "0" for documents to send)
            bpl_id: SAP Business Place ID for branch filtering (optional)
            last_sync_datetime: Last successful sync datetime (fetches documents updated after this time)

        Returns:
            List of delivery note dictionaries
        """
        if not self.session:
            if not self.login():
                raise ConnectionError("Failed to login to SAP B1")

        try:
            # Select fields (NO EXPAND)
            select_fields = (
                "DocObjectCode,U_ERPStatus,U_InvoiceStatus,DocEntry,DocNum,"
                "CardCode,CardName,DocumentStatus,DocType,DocDate,Cancelled,Comments,BPL_IDAssignedToInvoice,"
                "U_UUID,U_InvoiceSeriesNum,U_InvoiceProfile,"
                "UpdateDate,"
                "DocumentLines"
            )
            select_query = f"$select={select_fields}"

            # Build OData filter
            filter_conditions = [
                "U_ISArchived ne 'Y'",
                "Cancelled eq 'tNO'",
                f"U_ERPStatus eq '{erp_status}'",
                "U_ERPStatus ne ''",
                "U_ERPStatus ne '-'",
                "U_ERPStatus ne null"
            ]

            # Add branch filter if specified
            if bpl_id:
                filter_conditions.append(f"BPL_IDAssignedToInvoice eq {bpl_id}")

            # Add UpdateDate filter if last_sync_datetime provided
            if last_sync_datetime:
                # Format datetime to SAP OData format: yyyy-MM-ddTHH:mm:ss
                sync_date_str = last_sync_datetime.strftime('%Y-%m-%dT%H:%M:%S')
                filter_conditions.append(f"UpdateDate ge '{sync_date_str}'")
                _logger.info(f"Filtering delivery notes updated after: {sync_date_str}")

            filter_query = f"$filter={' and '.join(filter_conditions)}"

            query_string = f"{select_query}&{filter_query}"

            delivery_notes_url = f"{self.service_url}DeliveryNotes?{query_string}"

            _logger.info(f"Fetching SAP B1 delivery notes with ERPStatus={erp_status}")

            response = self.session.get(delivery_notes_url, timeout=60)

            if response.status_code == 200:
                result = response.json()
                delivery_notes = result.get("value", [])
                _logger.info(f"Fetched {len(delivery_notes)} delivery notes from SAP B1")
                return delivery_notes
            else:
                _logger.error(f"Failed to fetch delivery notes. Status: {response.status_code}, Response: {response.text}")
                return []

        except requests.exceptions.ConnectionError as e:
            error_msg = f"SAP B1'den irsaliye çekilirken bağlantı hatası oluştu. Lütfen ağ bağlantınızı kontrol edin.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.Timeout as e:
            error_msg = f"SAP B1'den irsaliye çekilirken zaman aşımı oluştu. Sunucu yanıt vermiyor.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"SAP B1'den irsaliye çekilirken hata oluştu.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except Exception as e:
            _logger.error(f"Exception while fetching delivery notes: {str(e)}")
            return []

    def update_invoice_status(self, doc_entry: int, uuid: str, status: str = "S"):
        """
        Update invoice status in SAP B1 after successful sync.

        Args:
            doc_entry: SAP DocEntry
            uuid: E-Invoice UUID
            status: New status ('S' for sent, 'E' for error, etc.)
        """
        if not self.session:
            if not self.login():
                raise ConnectionError("Failed to login to SAP B1")

        try:
            patch_url = f"{self.service_url}Invoices({doc_entry})"
            patch_data = {
                "U_UUID": uuid,
                "U_ERPStatus": status
            }

            response = self.session.patch(
                patch_url,
                json=patch_data,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code in [200, 204]:
                _logger.info(f"Updated SAP B1 invoice {doc_entry} status to {status}")
            else:
                _logger.error(f"Failed to update invoice status. Status: {response.status_code}, Response: {response.text}")

        except Exception as e:
            _logger.error(f"Exception while updating invoice status: {str(e)}")

    def fetch_business_partner(self, card_code: str) -> Optional[Dict[str, Any]]:
        """
        Fetch business partner (customer) details by CardCode.

        Args:
            card_code: SAP Business Partner CardCode

        Returns:
            Business partner dictionary or None
        """
        if not self.session:
            if not self.login():
                raise ConnectionError("Failed to login to SAP B1")

        try:
            # Select specific fields including UnifiedFederalTaxID (VKN/TCKN)
            select_fields = "CardCode,CardName,CardType,UnifiedFederalTaxID,FederalTaxID"
            bp_url = f"{self.service_url}BusinessPartners('{card_code}')?$select={select_fields}"

            _logger.info(f"Fetching BusinessPartner: {card_code}")

            response = self.session.get(bp_url, timeout=30)

            if response.status_code == 200:
                bp_data = response.json()
                _logger.info(f"Fetched BusinessPartner {card_code}")
                return bp_data
            else:
                _logger.error(f"Failed to fetch BusinessPartner. Status: {response.status_code}")
                return None

        except Exception as e:
            _logger.error(f"Exception while fetching BusinessPartner: {str(e)}")
            return None

    def update_delivery_note_status(self, doc_entry: int, uuid: str, status: str = "S"):
        """
        Update delivery note status in SAP B1 after successful sync.

        Args:
            doc_entry: SAP DocEntry
            uuid: E-Despatch UUID
            status: New status
        """
        if not self.session:
            if not self.login():
                raise ConnectionError("Failed to login to SAP B1")

        try:
            patch_url = f"{self.service_url}DeliveryNotes({doc_entry})"
            patch_data = {
                "U_UUID": uuid,
                "U_ERPStatus": status
            }

            response = self.session.patch(
                patch_url,
                json=patch_data,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code in [200, 204]:
                _logger.info(f"Updated SAP B1 delivery note {doc_entry} status to {status}")
            else:
                _logger.error(f"Failed to update delivery note status. Status: {response.status_code}")

        except Exception as e:
            _logger.error(f"Exception while updating delivery note status: {str(e)}")

    def sync_unit_mappings_to_odoo(self) -> int:
        """
        HELPER METHOD: Fetch unit mappings from SAP AL_ERP_EDON_OBIK and sync to Odoo models.
        This is a one-time/initial setup operation to populate algebra.base.document.unit
        and algebra.base.document.unit.erp.mapping from SAP data.

        Returns:
            Number of mappings synced

        Usage:
            Use this method during initial setup to populate unit codes from SAP B1.
            After initial setup, manage units directly in Odoo UI.
        """
        if not self.session:
            if not self.login():
                raise ConnectionError("Failed to login to SAP B1")

        if not self.env:
            raise ValueError("Odoo environment required for syncing to models")

        try:
            query_url = f"{self.service_url}QueryService_PostQuery"

            query_data = {
                "QueryPath": "$crossjoin(AL_ERP_EDON_OBIK,AL_ERP_EDON_OBIK/ERP_EDON_BIK1Collection)",
                "QueryOption": "$expand=AL_ERP_EDON_OBIK($select=U_Code,U_Description),AL_ERP_EDON_OBIK/ERP_EDON_BIK1Collection($select=U_SAPCode,U_Description)&$filter=AL_ERP_EDON_OBIK/Code eq AL_ERP_EDON_OBIK/ERP_EDON_BIK1Collection/Code"
            }

            _logger.info("Fetching SAP B1 unit mappings from AL_ERP_EDON_OBIK for Odoo sync")

            response = self.session.post(
                query_url,
                json=query_data,
                headers={"Content-Type": "application/json"},
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                synced_count = 0

                # Parse crossjoin results and create/update Odoo records
                for item in result.get("value", []):
                    obik = item.get("AL_ERP_EDON_OBIK", {})
                    bik1_collection = item.get("ERP_EDON_BIK1Collection", {})

                    ubl_code = obik.get("U_Code")
                    ubl_description = obik.get("U_Description")
                    sap_code = bik1_collection.get("U_SAPCode")
                    sap_description = bik1_collection.get("U_Description")

                    if not sap_code or not ubl_code:
                        continue

                    # Get or create UBL unit
                    unit = self.env['algebra.base.document.unit'].search([
                        ('code', '=', ubl_code)
                    ], limit=1)

                    if not unit:
                        unit = self.env['algebra.base.document.unit'].create({
                            'code': ubl_code,
                            'name': ubl_description or ubl_code,
                            'description': f'Imported from SAP AL_ERP_EDON_OBIK'
                        })
                        _logger.info(f"Created UBL unit: {ubl_code}")

                    # Get or create ERP mapping
                    mapping = self.env['algebra.base.document.unit.erp.mapping'].search([
                        ('erp_system', '=', 'SAP_B1'),
                        ('erp_code', '=', sap_code)
                    ], limit=1)

                    if not mapping:
                        self.env['algebra.base.document.unit.erp.mapping'].create({
                            'unit_id': unit.id,
                            'erp_system': 'SAP_B1',
                            'erp_code': sap_code,
                            'erp_description': sap_description or f'SAP unit for {ubl_code}'
                        })
                        synced_count += 1
                        _logger.info(f"Created mapping: SAP '{sap_code}' -> UBL '{ubl_code}'")

                _logger.info(f"Synced {synced_count} unit mappings from SAP B1 to Odoo")
                return synced_count

            else:
                _logger.error(f"Failed to fetch unit mappings. Status: {response.status_code}, Response: {response.text}")
                return 0

        except Exception as e:
            _logger.error(f"Exception while syncing unit mappings: {str(e)}")
            return 0

    def sync_branches_to_odoo(self) -> int:
        """
        Fetch branches from SAP BusinessPlaces and sync to Odoo models.
        This is a setup operation to populate algebra.base.branch
        and algebra.base.branch.erp.mapping from SAP data.

        Returns:
            Number of branches synced

        Usage:
            Use this method to populate branch data from SAP B1.
            Can be triggered from settings UI.
        """
        if not self.session:
            if not self.login():
                raise ConnectionError("Failed to login to SAP B1")

        if not self.env:
            raise ValueError("Odoo environment required for syncing to models")

        try:
            # Fetch BusinessPlaces from SAP B1
            bp_url = f"{self.service_url}BusinessPlaces"
            select_fields = "BPLID,BPLName,MainBPL,Disabled,Street,City,County,ZipCode,Country"
            bp_url += f"?$select={select_fields}"

            _logger.info("Fetching SAP B1 BusinessPlaces")

            response = self.session.get(bp_url, timeout=30)

            if response.status_code == 200:
                result = response.json()
                business_places = result.get("value", [])
                synced_count = 0

                for bp in business_places:
                    bpl_id = str(bp.get('BPLID'))
                    bpl_name = bp.get('BPLName')
                    is_disabled = bp.get('Disabled') == 'tYES'

                    if not bpl_id or not bpl_name:
                        continue

                    # Get or create branch
                    branch = self.env['algebra.base.branch'].search([
                        ('code', '=', bpl_id)
                    ], limit=1)

                    branch_vals = {
                        'code': bpl_id,
                        'name': bpl_name,
                        'active': not is_disabled,
                        'street': bp.get('Street') or '',
                        'city': bp.get('City') or '',
                        'county': bp.get('County') or '',
                        'postal_code': bp.get('ZipCode') or '',
                        'country_code': bp.get('Country') or 'TR',
                        'description': f"SAP B1 BusinessPlace ID: {bpl_id}"
                    }

                    if not branch:
                        branch = self.env['algebra.base.branch'].create(branch_vals)
                        _logger.info(f"Created branch: {bpl_id} - {bpl_name}")
                    else:
                        branch.write(branch_vals)
                        _logger.info(f"Updated branch: {bpl_id} - {bpl_name}")

                    # Get or create ERP mapping
                    mapping = self.env['algebra.base.branch.erp.mapping'].search([
                        ('erp_system', '=', 'SAP_B1'),
                        ('erp_branch_id', '=', bpl_id)
                    ], limit=1)

                    mapping_vals = {
                        'branch_id': branch.id,
                        'erp_system': 'SAP_B1',
                        'erp_branch_id': bpl_id,
                        'erp_branch_name': bpl_name
                    }

                    if not mapping:
                        self.env['algebra.base.branch.erp.mapping'].create(mapping_vals)
                        synced_count += 1
                        _logger.info(f"Created branch mapping: SAP BPLId '{bpl_id}'")
                    else:
                        mapping.write(mapping_vals)

                _logger.info(f"Synced {synced_count} branches from SAP B1 to Odoo")
                return synced_count

            else:
                _logger.error(f"Failed to fetch BusinessPlaces. Status: {response.status_code}")
                return 0

        except requests.exceptions.ConnectionError as e:
            error_msg = f"SAP B1'den şube bilgileri çekilirken bağlantı hatası oluştu. Lütfen ağ bağlantınızı kontrol edin.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.Timeout as e:
            error_msg = f"SAP B1'den şube bilgileri çekilirken zaman aşımı oluştu. Sunucu yanıt vermiyor.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"SAP B1'den şube bilgileri çekilirken hata oluştu.\nDetay: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        except Exception as e:
            _logger.error(f"Exception while syncing branches: {str(e)}")
            raise UserError(f"Şube senkronizasyonu sırasında beklenmeyen bir hata oluştu: {str(e)}")

    def get_ubl_unit_code(self, sap_uom_code: str) -> Optional[str]:
        """
        Get UBL unit code for a given SAP UoMCode from Odoo model.

        Args:
            sap_uom_code: SAP B1 UoMCode (e.g., 'AD', 'KG', 'LT')

        Returns:
            UBL unit code (e.g., 'C62', 'KGM', 'LTR') or None if not found
        """
        if not sap_uom_code or not self.env:
            return None

        # Query algebra.base.document.unit.erp.mapping model
        mapping = self.env['algebra.base.document.unit.erp.mapping'].search([
            ('erp_system', '=', 'SAP_B1'),
            ('erp_code', '=', sap_uom_code)
        ], limit=1)

        if mapping and mapping.unit_id:
            _logger.debug(f"Unit mapping found: SAP '{sap_uom_code}' -> UBL '{mapping.unit_id.code}'")
            return mapping.unit_id.code

        _logger.warning(f"No unit mapping found for SAP code: {sap_uom_code}")
        return None

    def __enter__(self):
        """Context manager entry."""
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.logout()
