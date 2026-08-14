# -*- coding: utf-8 -*-
import json
from datetime import datetime

from odoo import models, fields


class UBLInvoiceStatusUyumsoftExt(models.Model):
    _inherit = "l10n_tr.ubl.invoice"

    uyumsoft_document_answer = fields.Selection(
        [
            ("none", "—"),
            ("waiting", "Waiting"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
        ],
        string="Document Answer (Uyumsoft)",
        readonly=True,
    )
    uyumsoft_outgoing_raw = fields.Text(
        string="Uyumsoft Raw Response",
        readonly=True,
        help="JSON data returned by the integrator via 'Fetch Integrator Status'",
    )
    uyumsoft_outgoing_fetch_date = fields.Datetime(
        string="Last Uyumsoft Query Date",
        readonly=True,
    )

    def _on_outgoing_status_fetched(self, result, client):
        """Uyumsoft'a özgü alanları doldurur (bkz. invoice_integrator_sync.py hook'u)."""
        if client.code != "UYUMSOFT":
            return super()._on_outgoing_status_fetched(result, client)
        raw = result.get("raw") or {}
        raw_answer = (raw.get("AnswerType") or raw.get("documentAnswer") or "none")
        document_answer = client.translate_answer(str(raw_answer).strip().lower())
        self.write({
            "uyumsoft_outgoing_raw": json.dumps(raw, ensure_ascii=False, indent=2, default=str),
            "uyumsoft_outgoing_fetch_date": datetime.now(),
            "uyumsoft_document_answer": document_answer,
        })
