from odoo import models, fields, api, _


class UBLInvoiceIstisna(models.Model):
    _inherit = "l10n_tr.ubl.invoice"
    # İstisna profili için ek alan gerekmedikçe boş bırakılabilir
    # Satır bazında tax_exemption_reason_id invoice_line'da zaten mevcut
