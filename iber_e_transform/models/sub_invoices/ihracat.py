from odoo import models, fields, api, _

EXPORT_EXEMPTION_CODES = [
    ("218", "218 - Gümrük antrepoları ile ilgili hizmetler"),
    ("235", "235 - Transit ve Gümrük Antrepo Rejimi mallarının teslimi"),
    ("301", "301 - Mal ihracatı"),
    ("302", "302 - Hizmet ihracatı"),
    ("338", "338 - İmalatçıların Mal İhracatları"),
]

INCOTERMS = [
    ("CFR", "CFR - Mal bedeli ve navlunu ödenmiş teslim"),
    ("CIF", "CIF - Mal bedeli, sigorta ve navlunu ödenmiş teslim"),
    ("CIP", "CIP - Taşıma ve sigorta ücreti ödenmiş teslim"),
    ("CPT", "CPT - Taşıma ücreti ödenmiş teslim"),
    ("DDP", "DDP - Gümrük vergileri ödenmiş teslim"),
    ("EXW", "EXW - İşyerinde teslim"),
    ("FAS", "FAS - Gemi doğrultusunda teslim"),
    ("FCA", "FCA - Taşıyıcıya teslim"),
    ("FOB", "FOB - Gemi bordasında teslim"),
    ("DAP", "DAP - Belirlenen yerde teslim"),
]

TRANSPORTTYPES = [
    ("1", "Deniz Taşımacılığı"),
    ("2", "Demiryolu Taşımacılığı"),
    ("3", "Karayolu Taşımacılığı"),
    ("4", "Hava Taşımacılığı"),
    ("5", "Posta"),
    ("6", "Kombine Taşımacılık"),
    ("7", "Sabit Nakliyat"),
    ("8", "Ülke İçi Su Taşımacılığı"),
    ("9", "Uygun Olmayan Taşıma Şekli"),
]


class UBLInvoiceLineIhracat(models.Model):
    _inherit = "l10n_tr.ubl.invoiceline"

    gtip_num = fields.Char(string="GTIP No")
    incoterm_code = fields.Selection(selection=INCOTERMS, string="Incoterm Code")
    transport_type = fields.Selection(selection=TRANSPORTTYPES, string="Transport Type")
    product_traceID = fields.Char("Product Trace ID")
    container_number = fields.Char("Container Number")
    container_count = fields.Integer("Container Count")
    container_type = fields.Selection(
        [("AE", "AEROSOL"), ("AM", "KORUMALI AMPUL"), ("AP", "KORUMASIZ AMPUL")],
        string="Container Type",
    )


class UBLInvoiceIhracat(models.Model):
    _inherit = "l10n_tr.ubl.invoice"

    delivery_street = fields.Char("Address (Street / Avenue / Neighborhood)")
    delivery_county = fields.Char("District")
    delivery_city = fields.Char("City")
    delivery_postal_code = fields.Char("Postal Code")
    delivery_country_code = fields.Char()
    delivery_country_name = fields.Char()

    def build_ubl_line_dict(self, line, idx, line_notes="", extra_taxes=None):
        res = super().build_ubl_line_dict(line, idx, line_notes=line_notes, extra_taxes=extra_taxes)
        if self.profile_id.code == "IHRACAT":
            res.update({
                "GTIPNum": line.gtip_num or "",
                "IncotermCode": line.incoterm_code or "",
                "TransportType": line.transport_type or "",
                "ProductTraceID": line.product_traceID or "",
                "ContainerNumber": line.container_number or "",
                "ContainerCount": line.container_count or 0,
                "ContainerType": line.container_type or "",
            })
        return res

    def getDeliveryAddress(self):
        self.ensure_one()
        return {
            "Street": self.delivery_street or "",
            "City": self.delivery_city or "",
            "District": self.delivery_county or "",
            "PostalCode": self.delivery_postal_code or "",
            "CountryCode": self.delivery_country_code or "",
            "CountryName": self.delivery_country_name or "",
        }

    def to_json(self):
        res = super().to_json()
        if self.profile_id.code == "IHRACAT":
            res.update({"DeliveryAddress": self.getDeliveryAddress()})
        return res
