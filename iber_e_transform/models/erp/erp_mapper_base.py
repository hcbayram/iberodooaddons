# -*- coding: utf-8 -*-
"""
Abstract Base Class for ERP Field Mapping
------------------------------------------
This module provides the foundation for mapping ERP system fields to Odoo UBL fields.
Each ERP system (SAP B1, Logo, Mikro, etc.) should implement its own mapper.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
from dateutil.parser import parse
import logging

_logger = logging.getLogger(__name__)


class ERPMapperBase(ABC):
    """
    Abstract base class for ERP field mapping.

    Each ERP system must implement:
    - map_invoice_header: Maps ERP invoice header to Odoo invoice fields
    - map_invoice_line: Maps ERP invoice line to Odoo invoice line fields
    - map_delivery_note_header: Maps ERP delivery note header to Odoo fields
    - map_delivery_note_line: Maps ERP delivery note line to Odoo fields
    """

    def __init__(self, env):
        """
        Initialize mapper with Odoo environment.

        Args:
            env: Odoo environment object
        """
        self.env = env
        self.erp_system_name = self.get_erp_system_name()

    @abstractmethod
    def get_erp_system_name(self) -> str:
        """Return the name of the ERP system (e.g., 'SAP_B1', 'LOGO', 'MIKRO')"""
        pass

    @abstractmethod
    def get_invoice_object_type(self) -> str:
        """Return the ERP object type for invoices (e.g., 'OINV' for SAP B1)"""
        pass

    @abstractmethod
    def get_delivery_note_object_type(self) -> str:
        """Return the ERP object type for delivery notes (e.g., 'ODLN' for SAP B1)"""
        pass

    @abstractmethod
    def map_invoice_header(self, erp_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map ERP invoice header data to Odoo invoice fields.

        Args:
            erp_data: Raw data from ERP system (invoice header)

        Returns:
            Dictionary with Odoo field names and values
        """
        pass

    @abstractmethod
    def map_invoice_line(self,doctype, erp_line_data: Dict[str, Any], line_num: int) -> Dict[str, Any]:
        """
        Map ERP invoice line data to Odoo invoice line fields.

        Args:
            erp_line_data: Raw data from ERP system (invoice line)
            line_num: Line number/sequence

        Returns:
            Dictionary with Odoo invoice line field names and values
        """
        pass

    @abstractmethod
    def map_delivery_note_header(self, erp_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map ERP delivery note header data to Odoo delivery note fields.

        Args:
            erp_data: Raw data from ERP system (delivery note header)

        Returns:
            Dictionary with Odoo field names and values
        """
        pass

    @abstractmethod
    def map_delivery_note_line(self, erp_line_data: Dict[str, Any], line_num: int) -> Dict[str, Any]:
        """
        Map ERP delivery note line data to Odoo delivery note line fields.

        Args:
            erp_line_data: Raw data from ERP system (delivery note line)
            line_num: Line number/sequence

        Returns:
            Dictionary with Odoo delivery note line field names and values
        """
        pass

    # === HELPER METHODS (can be overridden by subclasses) ===

    def get_or_create_currency(self, currency_code: str):
        """
        Get or create currency record.

        Args:
            currency_code: ISO currency code (e.g., 'TRY', 'USD', 'EUR')

        Returns:
            res.currency recordset
        """
        if not currency_code:
            return self.env.ref("base.TRY", raise_if_not_found=False)

        currency = self.env["res.currency"].search([("name", "=", currency_code)], limit=1)
        if not currency:
            _logger.warning(f"Currency {currency_code} not found, using TRY as default")
            currency = self.env.ref("base.TRY", raise_if_not_found=False)

        return currency

    def get_or_create_unit(self, unit_code: str):
        """
        Get or create UBL unit record.

        Args:
            unit_code: UBL unit code (e.g., 'C62', 'KGM', 'LTR')

        Returns:
            algebra.base.document.unit recordset or None
        """
        if not unit_code:
            return None

        unit = self.env["algebra.base.document.unit"].search([("code", "=", unit_code)], limit=1)
        if not unit:
            _logger.warning(f"UBL Unit code {unit_code} not found in database")
            return None

        return unit
    def get_or_create_profile_id(self, profile_code: str, profile_name: str = None):
        """
        Get or create invoice type.

        Args:
            profile_code: Invoice profile code (e.g., 'TEMELFATURA', 'TICARIFATURA')
            profile_name: Invoice profile name (optional)

        Returns:
            algebra.base.document.profile.id recordset
        """
        if not profile_code:
            return None
        try:
            profile_id = self.env["algebra.base.document.profile.id"].search([("code", "=", profile_code)], limit=1)
        except Exception as e:
            _logger.error(f"Error fetching invoice type {profile_code}: {str(e)}")
        return profile_id
    
    def get_or_create_invoice_type(self, type_code: str, type_name: str = None):
        """
        Get or create invoice type.

        Args:
            type_code: Invoice type code (e.g., 'SATIS', 'IADE')
            type_name: Invoice type name (optional)

        Returns:
            algebra.base.document.type recordset
        """
        if not type_code:
            return None
        try:
            inv_type = self.env["algebra.base.document.type"].search([("code", "=", type_code)], limit=1)
        except Exception as e:
            _logger.error(f"Error fetching invoice type {type_code}: {str(e)}")
            
        """ if not inv_type and type_name:
            inv_type = self.env["algebra.base.document.type"].create({
                "code": type_code,
                "name": type_name or type_code,
                "doc_type": "credit_note" if "IADE" in type_code.upper() else "invoice"
            }) """

        return inv_type

    def _determine_scheme_id(self, vkn_tckn: str) -> str:
        """
        VKN (10 hane) veya TCKN (11 hane) olduğunu belirler.

        Args:
            vkn_tckn: Vergi kimlik numarası (VKN veya TCKN)

        Returns:
            'VKN' veya 'TCKN'
        """
        if not vkn_tckn:
            return "VKN"
        numeric_only = "".join(filter(str.isdigit, str(vkn_tckn)))
        if len(numeric_only) == 11:
            return "TCKN"
        return "VKN"

    def safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            return float(value) if value not in (None, "", "NULL") else default
        except (ValueError, TypeError):
            return default

    def safe_int(self, value: Any, default: int = 0) -> int:
        """Safely convert value to int."""
        try:
            return int(value) if value not in (None, "", "NULL") else default
        except (ValueError, TypeError):
            return default

    def safe_str(self, value: Any, default: str = "") -> str:
        """Safely convert value to string."""
        if value in (None, "NULL"):
            return default
        return str(value).strip()

    def parse_date(self, date_value: Any) -> Optional[str]:
        """
        Parse date from ERP format to Odoo format (YYYY-MM-DD).

        Args:
            date_value: Date value from ERP (can be string, datetime, etc.)

        Returns:
            Date string in YYYY-MM-DD format or None
        """
        if not date_value or date_value == "NULL":
            return None

        # If already a string in correct format
        if isinstance(date_value, str) and len(date_value) == 10:
            return date_value

        # If datetime object
        if hasattr(date_value, 'strftime'):
            return date_value.strftime('%Y-%m-%d')
        
        if isinstance(date_value, str):
            dt = parse(date_value)
            return dt.strftime("%Y-%m-%d")
        return None
