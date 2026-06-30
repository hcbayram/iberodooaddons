from odoo import models, fields


class EDNLog(models.Model):
    _name = "edn.log"
    _description = "E-Dönüşüm İşlem Logu"
    _order = "create_date desc"
    _log_access = True

    document_no = fields.Char("Belge No")
    uuid = fields.Char("UUID")
    integrator = fields.Char("Entegratör Kodu")
    jsonpayload = fields.Text("JSON Payload")
    xmlpayload = fields.Text("XML Payload")
    payload = fields.Text("Ham İstek")
    result = fields.Text("Yanıt (JSON)")
    status = fields.Selection(
        [
            ("success", "Başarılı"),
            ("error", "Hata"),
            ("info", "Bilgi"),
        ],
        string="Durum",
        default="info",
    )
