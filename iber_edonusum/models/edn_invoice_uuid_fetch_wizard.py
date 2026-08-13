# -*- coding: utf-8 -*-
"""
Gelen e-Faturayı bilinen bir UUID (GUID) ile entegratörden doğrudan
çekme sihirbazı — bkz. invoice_integrator_sync.py:
action_fetch_by_uuid_from_integrator.
"""
from odoo import models, fields


class EdnInvoiceUuidFetchWizard(models.TransientModel):
    _name = "edn.invoice.uuid.fetch.wizard"
    _description = "Gelen e-Fatura: UUID İle Getir"

    doc_uuid = fields.Char("Fatura UUID (GUID)", required=True)

    def action_fetch(self):
        self.ensure_one()
        return self.env["l10n_tr.ubl.invoice"].action_fetch_by_uuid_from_integrator(
            self.doc_uuid
        )
