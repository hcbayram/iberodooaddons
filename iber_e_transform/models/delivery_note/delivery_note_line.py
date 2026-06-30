from odoo import models, fields, api, _


class UBLDeliveryNoteLine(models.Model):
    _name = "l10n_tr.ubl.delivery.note.line"
    _description = "UBL-TR Delivery Note Line"
    _inherit = "algebra.base.document.line"

    base_document_id = fields.Many2one(
        "l10n_tr.ubl.delivery.note",
        string="Delivery Note",
        ondelete="cascade",
        index=True,
        required=True,
    )
    line_note_ids = fields.One2many(
        "l10n_tr.ubl.delivery.note.line.note",
        "line_id",
        string="Line Notes",
    )


class UBLDeliveryNoteLineNote(models.Model):
    _name = "l10n_tr.ubl.delivery.note.line.note"
    _description = "UBL Delivery Note Line Notes"
    _order = "sequence,id"

    line_id = fields.Many2one(
        "l10n_tr.ubl.delivery.note.line",
        string="Line",
        ondelete="cascade",
        required=True,
    )
    sequence = fields.Integer(default=10)
    note = fields.Text("Line Note", required=True)
