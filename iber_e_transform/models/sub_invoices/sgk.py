from odoo import models, fields, api, _

SGK_INVOICE_TYPES = [
    ("SAGLIK_ECZ", "Eczane"),
    ("SAGLIK_HAS", "Hastane"),
    ("SAGLIK_OPT", "Optik"),
    ("SAGLIK_MED", "Medikal"),
    ("ABONELIK", "Abonelik"),
    ("MAL_HIZMET", "Mal/Hizmet"),
    ("DIGER", "Diğer"),
]


class UBLInvoice(models.Model):
    _inherit = "l10n_tr.ubl.invoice"

    
    sgk_invoice_type = fields.Selection(
        selection=SGK_INVOICE_TYPES, string="SGK Invoice Type")
    sgk_company_code = fields.Char(string="SGK Company Code")
    sgk_company_name = fields.Char(string="SGK Company Name")
    sgk_file_number = fields.Char(string="SGK File Number")

    
""" <cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>
	<cbc:AccountingCost>DIGER</cbc:AccountingCost>
	.
	.
	<cac:AdditionalDocumentReference>
		<cbc:ID/>
		<cbc:IssueDate>2025-11-06</cbc:IssueDate>
		<cbc:DocumentTypeCode>MUKELLEF_KODU</cbc:DocumentTypeCode>
		<cbc:DocumentType>sd</cbc:DocumentType>
		<cbc:DocumentDescription>Sgk Mükellef Kodu</cbc:DocumentDescription>
	</cac:AdditionalDocumentReference>
	<cac:AdditionalDocumentReference>
		<cbc:ID/>
		<cbc:IssueDate>2025-11-06</cbc:IssueDate>
		<cbc:DocumentTypeCode>MUKELLEF_ADI</cbc:DocumentTypeCode>
		<cbc:DocumentType>sd</cbc:DocumentType>
		<cbc:DocumentDescription>Sgk Mükellef Adı</cbc:DocumentDescription>
	</cac:AdditionalDocumentReference>
	<cac:AdditionalDocumentReference>
		<cbc:ID/>
		<cbc:IssueDate>2025-11-06</cbc:IssueDate>
		<cbc:DocumentTypeCode>DOSYA_NO</cbc:DocumentTypeCode>
		<cbc:DocumentType>sd</cbc:DocumentType>
		<cbc:DocumentDescription>Sgk Dosya No</cbc:DocumentDescription>
	</cac:AdditionalDocumentReference> """
