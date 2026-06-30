"""
Odoo 19 Enterprise ERP Mapper
-------------------------------
Maps account.move → l10n_tr.ubl.invoice
Maps stock.picking → l10n_tr.ubl.delivery.note

Implements ERPMapperBase for Odoo native integration.
"""
from .erp_mapper_base import ERPMapperBase
from typing import Dict, Any
import logging

_logger = logging.getLogger(__name__)


class OdooERPMapper(ERPMapperBase):
    """Maps Odoo 19 Enterprise native records to UBL-TR structures."""

    def get_erp_system_name(self) -> str:
        return "ODOO19"

    def get_invoice_object_type(self) -> str:
        return "account.move"

    def get_delivery_note_object_type(self) -> str:
        return "stock.picking"

    # ========================================
    # INVOICE HEADER: account.move → ubl.invoice
    # ========================================
    def map_invoice_header(self, move, **kwargs) -> Dict[str, Any]:
        """
        Map Odoo account.move to l10n_tr.ubl.invoice fields.

        Args:
            move: account.move recordset
        """
        settings = self.env["ubl21.config.settings"].get_singleton()
        company = move.company_id
        partner = move.partner_id

        # VKN/TCKN from partner.vat
        customer_vkn = self._clean_vkn(partner.vat or "")
        supplier_vkn = self._clean_vkn(company.partner_id.vat or "")

        # Profile auto-detect: EARSIVFATURA for B2C, TICARIFATURA for B2B
        profile_code = self._detect_invoice_profile(customer_vkn, partner)
        profile_id = self.get_or_create_profile_id(profile_code)

        # Document type
        doc_type_code = "IADE" if move.move_type == "out_refund" else "SATIS"
        doc_type = self.get_or_create_invoice_type(doc_type_code)

        # Currency
        currency = self.get_or_create_currency(move.currency_id.name)

        vals = {
            # ERP tracking
            "erp_id": str(move.id),
            "erp_object_type": self.get_invoice_object_type(),
            "account_move_id": move.id,

            # UBL header
            "id_value": move.name or "/",
            "issue_date": move.invoice_date or self.env.fields.Date.context_today(),
            "document_currency_id": currency.id if currency else False,
            "document_exchange_rate": move.currency_id.rate if hasattr(move.currency_id, "rate") else 1.0,
            "invoice_direction": "outgoing",

            # Supplier (company)
            "supplier_name": company.name or "",
            "supplier_vkn_tckn": supplier_vkn,
            "supplier_scheme_id": self._determine_scheme_id(supplier_vkn),
            "supplier_tax_office": company.partner_id.state_id.name or "",
            "supplier_street": company.partner_id.street or "",
            "supplier_county": company.partner_id.street2 or "",
            "supplier_city": company.partner_id.city or "",
            "supplier_postal_code": company.partner_id.zip or "",
            "supplier_country_code": company.partner_id.country_id.code or "TR",
            "supplier_country_name": company.partner_id.country_id.name or "TÜRKİYE",

            # Customer (partner)
            "customer_name": partner.name or "",
            "customer_vkn_tckn": customer_vkn,
            "customer_scheme_id": self._determine_scheme_id(customer_vkn),
            "customer_tax_office": partner.state_id.name or "",
            "customer_street": partner.street or "",
            "customer_county": partner.street2 or "",
            "customer_city": partner.city or "",
            "customer_postal_code": partner.zip or "",
            "customer_country_code": partner.country_id.code or "TR",
            "customer_country_name": partner.country_id.name or "TÜRKİYE",

            # Payment
            "PaymentDueDate": move.invoice_date_due,
            "PaymentMeansCode": "42",  # Havale/EFT default

            # Note
            "note": move.narration or "",
        }

        if profile_id:
            vals["profile_id"] = profile_id.id
        if doc_type:
            vals["document_type_id"] = doc_type.id

        # Settings'den supplier bilgilerini override et (eğer doluysa)
        if settings:
            if settings.erp_company_name:
                vals["supplier_name"] = settings.erp_company_name
            if settings.erp_vkn_tckn:
                vals["supplier_vkn_tckn"] = settings.erp_vkn_tckn
                vals["supplier_scheme_id"] = self._determine_scheme_id(settings.erp_vkn_tckn)
            if settings.erp_tax_office:
                vals["supplier_tax_office"] = settings.erp_tax_office
            if settings.erp_street:
                vals["supplier_street"] = settings.erp_street
            if settings.erp_city:
                vals["supplier_city"] = settings.erp_city

        return vals

    # ========================================
    # INVOICE LINE: account.move.line → ubl.invoiceline
    # ========================================
    def map_invoice_line(self, move_type, move_line, line_num: int, **kwargs) -> Dict[str, Any]:
        """
        Map Odoo account.move.line to l10n_tr.ubl.invoiceline fields.

        Args:
            move_type: move_type string (out_invoice, out_refund, etc.)
            move_line: account.move.line recordset
            line_num: line sequence number
        """
        product = move_line.product_id
        qty = move_line.quantity

        # KDV %
        tax_percent = 0.0
        tax_lines = move_line.tax_ids.filtered(lambda t: t.amount_type == "percent" and t.amount > 0)
        if tax_lines:
            tax_percent = tax_lines[0].amount

        # Birim kodu (Odoo UoM → UBL)
        uom_name = move_line.product_uom_id.name if move_line.product_uom_id else ""
        unit_record = self._map_uom_to_ubl(uom_name)

        vals = {
            "name": product.name if product else (move_line.name or ""),
            "description": move_line.name or "",
            "quantity": qty,
            "price_amount": move_line.price_unit,
            "currency_id": move_line.currency_id.id or move_line.move_id.currency_id.id,
            "tax_percent": tax_percent,
            "sellersItemId": product.default_code or "",
        }

        if unit_record:
            vals["unit_code_id"] = unit_record.id

        return vals

    # ========================================
    # DELIVERY NOTE HEADER: stock.picking → ubl.delivery.note
    # ========================================
    def map_delivery_note_header(self, picking, **kwargs) -> Dict[str, Any]:
        """
        Map Odoo stock.picking to l10n_tr.ubl.delivery.note fields.

        Args:
            picking: stock.picking recordset
        """
        settings = self.env["ubl21.config.settings"].get_singleton()
        company = picking.company_id
        partner = picking.partner_id or self.env["res.partner"]

        customer_vkn = self._clean_vkn(partner.vat or "") if partner else ""
        supplier_vkn = self._clean_vkn(company.partner_id.vat or "")

        profile_id = self.get_or_create_profile_id("TEMELIRSALIYE")
        currency = self.get_or_create_currency("TRY")

        vals = {
            # ERP tracking
            "erp_id": str(picking.id),
            "erp_object_type": self.get_delivery_note_object_type(),
            "stock_picking_id": picking.id,

            # UBL header
            "id_value": picking.name or "/",
            "issue_date": picking.scheduled_date.date() if picking.scheduled_date else False,
            "document_direction": "outgoing",
            "document_currency_id": currency.id if currency else False,

            # Supplier
            "supplier_name": company.name or "",
            "supplier_vkn_tckn": supplier_vkn,
            "supplier_scheme_id": self._determine_scheme_id(supplier_vkn),
            "supplier_street": company.partner_id.street or "",
            "supplier_county": company.partner_id.street2 or "",
            "supplier_city": company.partner_id.city or "",
            "supplier_postal_code": company.partner_id.zip or "",
            "supplier_country_code": company.partner_id.country_id.code or "TR",
            "supplier_country_name": company.partner_id.country_id.name or "TÜRKİYE",

            # Customer
            "customer_name": partner.name or "" if partner else "",
            "customer_vkn_tckn": customer_vkn,
            "customer_scheme_id": self._determine_scheme_id(customer_vkn),
            "customer_street": partner.street or "" if partner else "",
            "customer_county": partner.street2 or "" if partner else "",
            "customer_city": partner.city or "" if partner else "",
            "customer_postal_code": partner.zip or "" if partner else "",
            "customer_country_code": partner.country_id.code or "TR" if partner else "TR",
            "customer_country_name": partner.country_id.name or "TÜRKİYE" if partner else "TÜRKİYE",

            # Sevk tarihi
            "actual_despatch_date": picking.date_done.date() if picking.date_done else False,
        }

        if profile_id:
            vals["profile_id"] = profile_id.id

        # Settings'den override
        if settings and settings.erp_company_name:
            vals["supplier_name"] = settings.erp_company_name
        if settings and settings.erp_vkn_tckn:
            vals["supplier_vkn_tckn"] = settings.erp_vkn_tckn

        return vals

    # ========================================
    # DELIVERY NOTE LINE: stock.move → ubl.delivery.note.line
    # ========================================
    def map_delivery_note_line(self, move, line_num: int, **kwargs) -> Dict[str, Any]:
        """
        Map Odoo stock.move to l10n_tr.ubl.delivery.note.line fields.

        Args:
            move: stock.move recordset
            line_num: line sequence number
        """
        product = move.product_id
        uom_name = move.product_uom.name if move.product_uom else ""
        unit_record = self._map_uom_to_ubl(uom_name)
        currency = self.get_or_create_currency("TRY")

        vals = {
            "name": product.name if product else (move.description_picking or ""),
            "description": move.description_picking or "",
            "quantity": move.quantity,
            "price_amount": product.standard_price if product else 0.0,
            "currency_id": currency.id if currency else False,
        }

        if unit_record:
            vals["unit_code_id"] = unit_record.id

        return vals

    # ========================================
    # HELPERS
    # ========================================
    def _clean_vkn(self, vat: str) -> str:
        """Remove country prefix from VAT number (TR1234567890 → 1234567890)."""
        if not vat:
            return ""
        cleaned = "".join(filter(str.isdigit, vat))
        return cleaned

    def _detect_invoice_profile(self, customer_vkn: str, partner) -> str:
        """
        Detect invoice profile based on customer type.
        - B2B (VKN 10 digits): TICARIFATURA
        - B2C (TCKN 11 digits or no VKN): EARSIVFATURA
        """
        if customer_vkn and len(customer_vkn) == 10:
            return "TICARIFATURA"
        return "EARSIVFATURA"

    def _map_uom_to_ubl(self, uom_name: str):
        """Map Odoo UoM name to UBL unit record via erp.mapping."""
        if not uom_name:
            return self.get_or_create_unit("C62")

        # Check ODOO19 erp mapping first
        mapping = self.env["algebra.base.document.unit.erp.mapping"].search([
            ("erp_system", "=", "ODOO19"),
            ("erp_code", "=", uom_name),
        ], limit=1)

        if mapping and mapping.unit_id:
            return mapping.unit_id

        # Common name mappings as fallback
        name_to_ubl = {
            "Adet": "C62", "adet": "C62", "Units": "C62",
            "kg": "KGM", "KG": "KGM", "Kilogram": "KGM",
            "g": "GRM", "Gram": "GRM",
            "L": "LTR", "Litre": "LTR", "lt": "LTR",
            "m": "MTR", "Metre": "MTR",
            "m²": "MTK", "m2": "MTK",
            "m³": "MTQ", "m3": "MTQ",
            "h": "HUR", "Saat": "HUR",
            "Gün": "DAY",
        }
        ubl_code = name_to_ubl.get(uom_name, "C62")
        return self.get_or_create_unit(ubl_code)
