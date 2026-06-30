from odoo import models, fields


class PartyIDType(models.Model):
    _name = "l10n_tr.ubl.partyid.type"
    _description = "UBL-TR Party ID Type"

    name = fields.Char("Name", required=True)
    scheme_code = fields.Char("Scheme Code", required=True)
    description = fields.Char("Description")
    active = fields.Boolean("Active", default=True)
