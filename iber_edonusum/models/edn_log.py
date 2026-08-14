from odoo import models, fields


class EDNLog(models.Model):
    _name = "edn.log"
    _description = "e-Transformation Operation Log"
    _order = "create_date desc"
    _log_access = True

    document_no = fields.Char("Document No")
    uuid = fields.Char("UUID")
    integrator = fields.Char("Integrator Code")
    jsonpayload = fields.Text("JSON Payload")
    xmlpayload = fields.Text("XML Payload")
    payload = fields.Text("Raw Request")
    result = fields.Text("Response (JSON)")
    status = fields.Selection(
        [
            ("success", "Success"),
            ("error", "Error"),
            ("info", "Info"),
        ],
        string="Status",
        default="info",
    )
