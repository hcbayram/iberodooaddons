from odoo import models
from .ubl_invoice import InvoiceBuilder


class EArsivBuilder(InvoiceBuilder):
    def _apply_document_type_rules(self, inv, payload):
        inv.ProfileID.value = "EARSIVFATURA"
        return inv
    

class UBLEArchiveBuilder(models.AbstractModel):
    _name = "algebra.ubl.earchive"
    _inherit = "algebra.ubl.invoice"

    _builder_class = EArsivBuilder
