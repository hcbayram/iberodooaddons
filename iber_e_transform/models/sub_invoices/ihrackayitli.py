from odoo import models, fields, api, _

IHRAC_EXEMPTION_CODES = [
    ("701", "701 - 3065 s. KDV Kanununun 11/1-c md. Kapsamındaki İhraç Kayıtlı Satış"),
    ("702", "702 - DİİB ve Geçici Kabul Rejimi Kapsamındaki Satışlar"),
    ("703", "703 - 4760 s. ÖTV Kanununun 8/2 Md. Kapsamındaki İhraç Kayıtlı Satış"),
    ("704", "704 - 3065 sayılı KDV Kanununun (11/1-c) maddesi ve 4760 s. Ötv Kanununun 8/2. Md. Kapsamındaki İhraç Kayıtlı Satış"),
]


class UBLInvoiceLine(models.Model):
    _inherit = "l10n_tr.ubl.invoiceline"

    
    # ExportTaxExemptionReasonCode = fields.Selection(
    #     selection=IHRAC_EXEMPTION_CODES, string="Export Tax Exemption Reason Code", help="Export Tax Exemption Reason Code as per UBL-TR") 
    buyer_linenum = fields.Char(string="Buyer Line Number", help="Buyer Line Number for Export Registered Invoices")

    """ <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="TRY">2550</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="TRY">510</cbc:TaxAmount>
        <cbc:Percent>20</cbc:Percent>
        <cac:TaxCategory>
            <cbc:TaxExemptionReasonCode>701</cbc:TaxExemptionReasonCode>
            <cbc:TaxExemptionReason>701 - 3065 s. KDV Kanununun 11/1-c md. Kapsamındaki İhraç Kayıtlı Satış</cbc:TaxExemptionReason>
            <cac:TaxScheme>
                <cbc:Name>KDV</cbc:Name>
                <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
            </cac:TaxScheme>
        </cac:TaxCategory>
    </cac:TaxSubtotal> """