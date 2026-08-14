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
