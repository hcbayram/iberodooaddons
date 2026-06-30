from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """Odoo 19 account.move extension for e-transformation integration."""
    _inherit = "account.move"

    ubl_invoice_ids = fields.One2many(
        "l10n_tr.ubl.invoice",
        "account_move_id",
        string="UBL Faturalar",
    )
    ubl_invoice_count = fields.Integer(
        string="UBL Fatura Sayısı",
        compute="_compute_ubl_invoice_count",
    )
    ubl_status = fields.Selection(
        [
            ("none", "UBL Oluşturulmadı"),
            ("draft", "UBL Taslak"),
            ("sent", "GIB'e Gönderildi"),
            ("approved", "Onaylandı"),
            ("rejected", "Reddedildi"),
        ],
        string="E-Dönüşüm Durumu",
        compute="_compute_ubl_status",
        store=True,
    )

    @api.depends("ubl_invoice_ids")
    def _compute_ubl_invoice_count(self):
        for move in self:
            move.ubl_invoice_count = len(move.ubl_invoice_ids)

    @api.depends("ubl_invoice_ids")
    def _compute_ubl_status(self):
        for move in self:
            if not move.ubl_invoice_ids:
                move.ubl_status = "none"
            else:
                move.ubl_status = "draft"

    def action_view_ubl_invoices(self):
        """Smart button: UBL fatura listesini aç."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "iber_e_transform.action_ubl_invoice_outgoing"
        )
        action["domain"] = [("account_move_id", "=", self.id)]
        action["context"] = {"default_account_move_id": self.id}
        if self.ubl_invoice_count == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.ubl_invoice_ids[0].id
        return action

    def action_create_ubl_invoice(self):
        """Odoo faturasından UBL fatura oluştur (Seçenek A)."""
        self.ensure_one()
        if self.move_type not in ["out_invoice", "out_refund"]:
            raise UserError(_("Sadece müşteri faturaları için UBL oluşturulabilir."))
        if self.state != "posted":
            raise UserError(_("UBL fatura oluşturmak için fatura onaylanmış olmalıdır."))

        from ..erp.odoo_native_connector import OdooNativeConnector
        from ..erp.odoo_native_mapper import OdooERPMapper

        mapper = OdooERPMapper(self.env)
        header_vals = mapper.map_invoice_header(self)
        header_vals["erp_last_sync_date"] = fields.Datetime.now()

        ubl_invoice = self.env["l10n_tr.ubl.invoice"].create(header_vals)

        # Satırları oluştur
        line_commands = []
        for idx, line in enumerate(
            self.invoice_line_ids.filtered(lambda l: l.display_type == "product"), start=1
        ):
            line_vals = mapper.map_invoice_line(self.move_type, line, idx)
            line_commands.append((0, 0, line_vals))
        ubl_invoice.write({"line_ids": line_commands})

        return {
            "type": "ir.actions.act_window",
            "name": _("UBL Fatura"),
            "res_model": "l10n_tr.ubl.invoice",
            "view_mode": "form",
            "res_id": ubl_invoice.id,
            "target": "current",
        }
