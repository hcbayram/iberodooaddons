from odoo import models, fields


class ERPFieldMappingInfoWizard(models.TransientModel):
    _name = "erp.field.mapping.info.wizard"
    _description = "ERP Alan Eşleşme Bilgisi"

    info_html = fields.Html("Bilgi", readonly=True)
