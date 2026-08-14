from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    """Odoo 19 stock.picking extension for e-transformation integration."""
    _inherit = "stock.picking"

    ubl_delivery_note_ids = fields.One2many(
        "l10n_tr.ubl.delivery.note",
        "stock_picking_id",
        string="UBL Despatch Advices",
    )
    ubl_delivery_note_count = fields.Integer(
        string="UBL Despatch Advice Count",
        compute="_compute_ubl_dn_count",
    )

    @api.depends("ubl_delivery_note_ids")
    def _compute_ubl_dn_count(self):
        for picking in self:
            picking.ubl_delivery_note_count = len(picking.ubl_delivery_note_ids)

    def action_view_ubl_delivery_notes(self):
        """Smart button: UBL irsaliye listesini aç."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "iber_e_transform.action_ubl_delivery_note_outgoing"
        )
        action["domain"] = [("stock_picking_id", "=", self.id)]
        action["context"] = {"default_stock_picking_id": self.id}
        if self.ubl_delivery_note_count == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.ubl_delivery_note_ids[0].id
        return action

    def action_create_ubl_delivery_note(self):
        """Odoo irsaliyesinden UBL e-irsaliye oluştur (Seçenek A)."""
        self.ensure_one()
        if self.picking_type_code != "outgoing":
            raise UserError(_("UBL despatch advice can only be created for outgoing shipments."))
        if self.state != "done":
            raise UserError(_("The shipment must be completed to create a UBL despatch advice."))

        from ..erp.odoo_native_connector import OdooNativeConnector
        from ..erp.odoo_native_mapper import OdooERPMapper

        mapper = OdooERPMapper(self.env)
        header_vals = mapper.map_delivery_note_header(self)
        header_vals["erp_last_sync_date"] = fields.Datetime.now()

        ubl_dn = self.env["l10n_tr.ubl.delivery.note"].create(header_vals)

        # Satırları oluştur
        line_commands = []
        for idx, move in enumerate(
            self.move_ids.filtered(lambda m: m.state != "cancel"), start=1
        ):
            line_vals = mapper.map_delivery_note_line(move, idx)
            line_commands.append((0, 0, line_vals))
        ubl_dn.write({"line_ids": line_commands})

        return {
            "type": "ir.actions.act_window",
            "name": _("UBL Despatch Advice"),
            "res_model": "l10n_tr.ubl.delivery.note",
            "view_mode": "form",
            "res_id": ubl_dn.id,
            "target": "current",
        }
