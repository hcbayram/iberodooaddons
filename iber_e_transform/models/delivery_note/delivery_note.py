from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import file_path
import json
import requests
import logging

_logger = logging.getLogger(__name__)

try:
    from ...utils.xslt_helper import xslt2_transform
    XSLT_AVAILABLE = True
except Exception:
    XSLT_AVAILABLE = False
    def xslt2_transform(xml_string, xslt_path):
        raise NotImplementedError("xslt_helper module could not be loaded. Is Saxon/lxml installed?")


class UBLDeliveryNote(models.Model):
    _name = "l10n_tr.ubl.delivery.note"
    _inherits = {"algebra.base.document": "base_document_id"}
    _inherit = ["algebra.base.e_document_base_methods"]
    _description = "UBL-TR 2.1 Delivery Note"
    _rec_name = "id_value"

    _xslt_path = "iber_e_transform/static/xslt/irsaliye.xslt"
    _profile_id_type = "delivery_note"

    base_document_id = fields.Many2one(
        "algebra.base.document",
        string="Base Document",
        auto_join=True,
        index=True,
        ondelete="cascade",
        required=True,
    )
    _sql_constraints = [
        ("unique_base_id", "unique(base_document_id)", "Each base document must have only one sub record!"),
    ]

    # Odoo 19 native bağlantısı (Seçenek A)
    stock_picking_id = fields.Many2one(
        "stock.picking",
        string="System Despatch Advice",
        index=True,
        ondelete="set null",
        help="The System stock move that is the source of this UBL despatch advice",
    )

    document_direction = fields.Selection(
        [("incoming", "Incoming Despatch Advice"), ("outgoing", "Outgoing Despatch Advice")],
        string="Despatch Direction",
        default="outgoing",
        required=True,
    )
    copy_indicator = fields.Boolean("Original/Copy", default=False)

    # Originator
    originator_name = fields.Char("Originator Party Name")
    originator_vkn_tckn = fields.Char("VKN/TCKN")
    originator_tax_office = fields.Char("Tax Office")
    originator_street = fields.Char("Address")
    originator_county = fields.Char("District")
    originator_city = fields.Char("City")
    originator_postal_code = fields.Char("Postal Code")
    originator_country_code = fields.Char(default="TR")
    originator_country_name = fields.Char(default="TÜRKİYE")

    # Carrier
    carrier_name = fields.Char("Carrier Name")
    carrier_vkn_tckn = fields.Char("VKN/TCKN")
    carrier_tax_office = fields.Char("Tax Office")
    carrier_street = fields.Char("Address")
    carrier_county = fields.Char("District")
    carrier_city = fields.Char("City")
    carrier_postal_code = fields.Char("Postal Code")
    carrier_country_code = fields.Char(default="TR")
    carrier_country_name = fields.Char(default="TÜRKİYE")

    # Buyer Customer
    buyercustomer_name = fields.Char("Buyer Party Name")
    buyercustomer_vkn_tckn = fields.Char("VKN/TCKN")
    buyercustomer_tax_office = fields.Char("Tax Office")
    buyercustomer_street = fields.Char("Address")
    buyercustomer_county = fields.Char("District")
    buyercustomer_city = fields.Char("City")
    buyercustomer_postal_code = fields.Char("Postal Code")
    buyercustomer_country_code = fields.Char(default="TR")
    buyercustomer_country_name = fields.Char(default="TÜRKİYE")

    # Seller Supplier
    sellersupplier_name = fields.Char("Seller Party Name")
    sellersupplier_vkn_tckn = fields.Char("VKN/TCKN")
    sellersupplier_tax_office = fields.Char("Tax Office")
    sellersupplier_street = fields.Char("Address")
    sellersupplier_county = fields.Char("District")
    sellersupplier_city = fields.Char("City")
    sellersupplier_postal_code = fields.Char("Postal Code")
    sellersupplier_country_code = fields.Char(default="TR")
    sellersupplier_country_name = fields.Char(default="TÜRKİYE")

    # Shipment
    shipment_id = fields.Char("Shipment ID")
    goods_item_value_amount = fields.Float("Goods Value", digits="Percentage Analytic")
    vehicle_plate_number = fields.Char("Vehicle Plate Number")
    trailer_ids = fields.One2many(
        "l10n_tr.ubl.delivery.note.trailer", "delivery_note_id", string="Trailer Plate Numbers"
    )
    driver_ids = fields.One2many(
        "l10n_tr.ubl.delivery.note.driver", "delivery_note_id", string="Drivers"
    )
    actual_despatch_date = fields.Date("Actual Despatch Date")
    actual_despatch_time = fields.Float("Actual Despatch Time")
    despatch_contact_name = fields.Char("Delivered By")

    line_ids = fields.One2many(
        "l10n_tr.ubl.delivery.note.line", "base_document_id", string="Lines"
    )

    def _get_service_url(self):
        self.ensure_one()
        config = self.env["ubl21.config.settings"].get_singleton()
        url = config.ubl_service_url
        if not url:
            raise UserError("UBL XML service address (UBL Service URL) is not defined.")
        return url

    def _get_profile_id_domain(self):
        return [("profile_type", "=", self._profile_id_type)]

    def _format_time(self, time_float):
        if not time_float:
            return ""
        hours = int(time_float)
        minutes = int((time_float - hours) * 60)
        return f"{hours:02d}:{minutes:02d}:00"

    def get_shipment_info(self):
        self.ensure_one()
        shipment = {
            "ShipmentID": self.shipment_id or "",
            "GoodsItemValueAmount": self.goods_item_value_amount or 0.0,
            "VehiclePlateNumber": self.vehicle_plate_number or "",
            "ActualDespatchDate": str(self.actual_despatch_date or ""),
            "ActualDespatchTime": self._format_time(self.actual_despatch_time) if self.actual_despatch_time else "",
        }
        trailer_plates = [t.plate_number for t in self.trailer_ids if t.plate_number]
        if trailer_plates:
            shipment["TrailerPlates"] = trailer_plates
        shipment["Delivery"] = {
            "DeliveryAddress": {
                "Street": self.customer_street or "",
                "City": self.customer_city or "",
                "District": self.customer_county or "",
                "PostalCode": self.customer_postal_code or "",
                "CountryCode": self.customer_country_code or "TR",
                "CountryName": self.customer_country_name or "TÜRKİYE",
            }
        }
        if self.carrier_name or self.carrier_vkn_tckn:
            shipment["Delivery"]["CarrierParty"] = {
                "SchemeID": "VKN" if self.carrier_vkn_tckn and len(self.carrier_vkn_tckn) == 10 else "TCKN",
                "SchemeValue": self.carrier_vkn_tckn or "",
                "Title": self.carrier_name or "",
                "TaxOffice": self.carrier_tax_office or "",
                "Address": {
                    "Street": self.carrier_street or "",
                    "City": self.carrier_city or "",
                    "District": self.carrier_county or "",
                    "PostalCode": self.carrier_postal_code or "",
                    "CountryCode": self.carrier_country_code or "TR",
                    "CountryName": self.carrier_country_name or "TÜRKİYE",
                },
                "PartyIdentifications": [],
            }
        shipment["Drivers"] = [
            {"Name": d.first_name or "", "Surname": d.family_name or "", "TCKN": d.tckn or ""}
            for d in self.driver_ids
        ]
        return shipment

    def get_lines(self):
        lines = []
        for idx, line in enumerate(self.line_ids):
            line_notes = [{"Note": n.note or ""} for n in line.line_note_ids]
            lines.append({
                "LineNum": idx + 1,
                "ItemCode": line.name or "",
                "ItemName": line.name or "",
                "Quantity": line.quantity,
                "UnitCode": line.unit_code or "NIU",
                "Notes": line_notes,
                "Description": line.description or "",
                "BrandName": line.brandName or "",
                "ModelName": line.modelName or "",
                "BuyersItemIdentification": line.buyersItemId or "",
                "SellersItemIdentification": line.sellersItemId or "",
                "ManufacturersItemIdentification": line.manufacturerItemId or "",
            })
        return lines

    def get_header(self):
        self.ensure_one()
        from datetime import date
        return {
            "DocNum": self.id_value,
            "DocDate": str(self.issue_date or date.today()),
            "UUID": getattr(self, "UUID", "") or "",
            "ProfileID": self.profile_id.code or "",
            "DespatchAdviceTypeCode": self.document_type_code or "",
        }

    def to_json(self):
        self.ensure_one()
        additional_parties = {}
        if self.buyercustomer_name or self.buyercustomer_vkn_tckn:
            additional_parties["BuyerCustomerParty"] = {
                "SchemeID": "VKN" if self.buyercustomer_vkn_tckn and len(self.buyercustomer_vkn_tckn) == 10 else "TCKN",
                "SchemeValue": self.buyercustomer_vkn_tckn or "",
                "Title": self.buyercustomer_name or "",
                "TaxOffice": self.buyercustomer_tax_office or "",
                "Address": {
                    "Street": self.buyercustomer_street or "",
                    "City": self.buyercustomer_city or "",
                    "District": self.buyercustomer_county or "",
                    "PostalCode": self.buyercustomer_postal_code or "",
                    "CountryCode": self.buyercustomer_country_code or "TR",
                    "CountryName": self.buyercustomer_country_name or "TÜRKİYE",
                },
                "PartyIdentifications": [],
            }
        if self.sellersupplier_name or self.sellersupplier_vkn_tckn:
            additional_parties["SellerSupplierParty"] = {
                "SchemeID": "VKN" if self.sellersupplier_vkn_tckn and len(self.sellersupplier_vkn_tckn) == 10 else "TCKN",
                "SchemeValue": self.sellersupplier_vkn_tckn or "",
                "Title": self.sellersupplier_name or "",
                "TaxOffice": self.sellersupplier_tax_office or "",
                "Address": {
                    "Street": self.sellersupplier_street or "",
                    "City": self.sellersupplier_city or "",
                    "District": self.sellersupplier_county or "",
                    "PostalCode": self.sellersupplier_postal_code or "",
                    "CountryCode": self.sellersupplier_country_code or "TR",
                    "CountryName": self.sellersupplier_country_name or "TÜRKİYE",
                },
                "PartyIdentifications": [],
            }
        if self.originator_name or self.originator_vkn_tckn:
            additional_parties["OriginatorCustomerParty"] = {
                "SchemeID": "VKN" if self.originator_vkn_tckn and len(self.originator_vkn_tckn) == 10 else "TCKN",
                "SchemeValue": self.originator_vkn_tckn or "",
                "Title": self.originator_name or "",
                "TaxOffice": self.originator_tax_office or "",
                "Address": {
                    "Street": self.originator_street or "",
                    "City": self.originator_city or "",
                    "District": self.originator_county or "",
                    "PostalCode": self.originator_postal_code or "",
                    "CountryCode": self.originator_country_code or "TR",
                    "CountryName": self.originator_country_name or "TÜRKİYE",
                },
                "PartyIdentifications": [],
            }
        result = {
            "DocumentType": "DespatchAdvice",
            "Header": self.get_header(),
            "Company": self.get_company(),
            "Customer": self.get_customer(),
            "Lines": self.get_lines(),
            "Notes": self.get_invoice_notes(),
            "Shipment": self.get_shipment_info(),
            "CopyIndicator": self.copy_indicator,
            "DespatchContactName": self.despatch_contact_name or "",
        }
        if additional_parties:
            result.update(additional_parties)
        return result

    def action_send_to_ubl_service(self):
        self.ensure_one()
        self.check_document_validity()
        xml_response = self._get_xml_from_service()
        json_payload = self.to_json()
        if not xml_response:
            raise UserError("Could not fetch XML from the service!")
        settings = self.env["ubl21.config.settings"].get_singleton()
        integrator_info = {
            "IntegratorCode": settings.integrator_id.code if settings and settings.integrator_id else "NES",
            "test_mode": settings.test_mode if settings else False,
            "user_name": settings.user_name if settings else "",
            "user_password": settings.user_password if settings else "",
            "api_token": settings.api_token if settings else "",
        }
        payload = {
            "IntegratorInfo": integrator_info,
            "DocumentType": "DespatchAdvice",
            "DocumentProfile": self.profile_id.code,
            "File": xml_response,
            "JsonPayload": json_payload,
            "UUID": self.UUID,
            "IsDirectSend": True,
            "PreviewType": "None",
            "SenderAlias": settings.erp_sender_alias,
            "ReceiverAlias": self.customer_receiver_alias,
            "CustomerRegisterNumber": self.customer_vkn_tckn,
        }
        try:
            if "edn.document.manager" in self.env:
                resp_data = self.env["edn.document.manager"].sudo().send_document(payload)
            else:
                url = self._get_service_url().rstrip("/") + "/send_ubl_xml"
                response = requests.post(url, headers=self._service_headers(), data=json.dumps(payload))
                if response.status_code != 200:
                    raise UserError(
                        _("Service returned an error (HTTP %s):\n%s") % (response.status_code, response.text[:300])
                    )
                resp_data = response.json()

            integrator_ok = resp_data.get("ok", True)
            integrator_error = resp_data.get("error") or ""
            envelope_id = resp_data.get("EnvelopeID") or resp_data.get("envelope_id") or ""

            if integrator_ok:
                self.write({
                    "gib_status": "sent",
                    "gib_envelope_id": envelope_id,
                    "gib_send_date": fields.Datetime.now(),
                })
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Sent to GIB"),
                        "message": _("Despatch advice sent successfully.\nUUID: %s") % self.UUID,
                        "type": "success",
                        "sticky": True,
                    },
                }
            else:
                self.write({"gib_status": "error", "gib_response_desc": integrator_error})
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Integrator Error"),
                        "message": integrator_error,
                        "type": "danger",
                        "sticky": True,
                    },
                }
        except UserError:
            raise
        except Exception as e:
            self.write({"gib_status": "error"})
            raise UserError(_("Send error: %s") % str(e))

    @api.model
    def action_sync_from_erp(self):
        """ERP sisteminden irsaliyeleri çeker. Alt modüller (iber_sap_b1 vb.) bu metodu genişletir."""
        settings = self.env["ubl21.config.settings"].get_singleton()
        if not settings:
            raise UserError("Settings not found.")
        return self._sync_from_odoo_native(settings)

    def _sync_from_odoo_native(self, settings):
        from ..erp.odoo_native_connector import OdooNativeConnector
        from ..erp.odoo_native_mapper import OdooERPMapper

        _logger.info("=== Odoo Native Despatch Advice Sync Started ===")
        connector = OdooNativeConnector(self.env)
        mapper = OdooERPMapper(self.env)
        last_sync = settings.last_delivery_note_sync_datetime
        sync_start_time = fields.Datetime.now()
        created_count = updated_count = error_count = 0

        pickings = connector.fetch_delivery_notes(last_sync_datetime=last_sync)
        for picking in pickings:
            try:
                picking_id_str = str(picking.id)
                existing = self.search([
                    ("erp_id", "=", picking_id_str),
                    ("erp_object_type", "=", mapper.get_delivery_note_object_type()),
                ], limit=1)
                header_vals = mapper.map_delivery_note_header(picking)
                header_vals["erp_last_sync_date"] = fields.Datetime.now()
                if existing:
                    existing.write(header_vals)
                    self._sync_dn_lines_from_odoo(existing, picking, mapper)
                    updated_count += 1
                else:
                    new_dn = self.create(header_vals)
                    self._sync_dn_lines_from_odoo(new_dn, picking, mapper)
                    created_count += 1
            except Exception as e:
                error_count += 1
                _logger.error("Error processing despatch advice %s: %s", picking.name, str(e))

        settings.write({"last_delivery_note_sync_datetime": sync_start_time})
        message = f"Sync completed.\nCreated: {created_count}\nUpdated: {updated_count}"
        if error_count:
            message += f"\nErrors: {error_count}"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Completed", "message": message, "type": "success", "sticky": False},
        }

    def _sync_dn_lines_from_odoo(self, delivery_note, picking, mapper):
        delivery_note.line_ids.unlink()
        line_commands = []
        for idx, move in enumerate(picking.move_ids.filtered(lambda m: m.state != "cancel"), start=1):
            line_vals = mapper.map_delivery_note_line(move, idx)
            line_commands.append((0, 0, line_vals))
        delivery_note.write({"line_ids": line_commands})



class UBLDeliveryNoteTrailer(models.Model):
    _name = "l10n_tr.ubl.delivery.note.trailer"
    _description = "Delivery Note Trailer (Dorse)"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    delivery_note_id = fields.Many2one(
        "l10n_tr.ubl.delivery.note", string="Delivery Note", required=True, ondelete="cascade"
    )
    plate_number = fields.Char("Trailer Plate Number", required=True)


class UBLDeliveryNoteDriver(models.Model):
    _name = "l10n_tr.ubl.delivery.note.driver"
    _description = "Delivery Note Driver"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    delivery_note_id = fields.Many2one(
        "l10n_tr.ubl.delivery.note", string="Delivery Note", required=True, ondelete="cascade"
    )
    first_name = fields.Char("First Name", required=True)
    family_name = fields.Char("Last Name", required=True)
    title = fields.Char("Title", default="Şoför")
    tckn = fields.Char("TCKN")


class UBLDeliveryNoteExt(models.Model):
    _inherit = "l10n_tr.ubl.delivery.note"

    def action_view_stock_picking(self):
        self.ensure_one()
        if not self.stock_picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.stock_picking_id.id,
            "target": "current",
        }
