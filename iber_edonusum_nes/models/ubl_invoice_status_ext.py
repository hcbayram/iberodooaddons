# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime
from odoo import models, fields, _

_logger = logging.getLogger(__name__)

class UBLInvoiceStatusExt(models.Model):
    _inherit = "l10n_tr.ubl.invoice"

    nes_document_answer = fields.Selection(
        [
            ("none", "—"),
            ("waiting", "Waiting"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
        ],
        string="Document Answer",
        readonly=True,
    )
    nes_outgoing_raw = fields.Text(
        string="NES Raw Response",
        readonly=True,
        help="JSON data returned by the integrator via 'Fetch Integrator Status'",
    )
    nes_outgoing_fetch_date = fields.Datetime(
        string="Last NES Query Date",
        readonly=True,
    )

    def _on_outgoing_status_fetched(self, result, client):
        """NES'e özgü alanları doldurur."""
        raw = result.get("raw") or {}
        raw_answer = (raw.get("documentAnswer") or "none").strip().lower()
        document_answer = client.translate_answer(raw_answer)

        self.write({
            "nes_outgoing_raw": json.dumps(raw, ensure_ascii=False, indent=2),
            "nes_outgoing_fetch_date": datetime.now(),
            "nes_document_answer": document_answer,
        })

    def action_preview_pdf(self):
        """
        PDF önizleme:
        - Gelen fatura veya gönderilmiş giden fatura → entegratörden PDF dene
        - Başarısızsa → standart (XSLT) önizlemeye geri dön, uyarı bildir
        """
        from odoo.exceptions import UserError
        self.ensure_one()
        integrator_code = self._get_integrator_code()
        use_integrator = (
            integrator_code and self.UUID and (
                self.invoice_direction == "incoming" or
                self.gib_status in ("sent", "approved", "rejected")
            )
        )
        integrator_warning = None
        if use_integrator:
            try:
                ok = self._fetch_and_store_pdf_from_integrator(integrator_code)
                if not ok:
                    integrator_warning = _("Could not fetch PDF from the integrator, using standard preview.")
                    use_integrator = False
            except Exception as e:
                integrator_warning = _("Integrator PDF error: %s\nUsing standard preview.") % str(e)
                use_integrator = False

        if not use_integrator:
            try:
                self.pdf_data = self.get_pdf_data()
            except Exception as e:
                raise UserError(_("Could not generate PDF:\n%s") % str(e))

        action = {
            "type": "ir.actions.act_window",
            "res_model": "l10n_tr.ubl.invoice",
            "view_mode": "form",
            "views": [(False, "form")],
            "res_id": self.id,
            "target": "current",
        }

        if integrator_warning:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("PDF Warning"),
                    "message": integrator_warning,
                    "type": "warning",
                    "sticky": False,
                    "next": action,
                },
            }
        return action
