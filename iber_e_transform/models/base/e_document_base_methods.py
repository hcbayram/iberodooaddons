from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import file_path
import json
import requests
import subprocess
import base64
import uuid as uuid_engine
import logging

_logger = logging.getLogger(__name__)

try:
    from ...utils.xslt_helper import xslt2_transform
    XSLT_AVAILABLE = True
except Exception:
    XSLT_AVAILABLE = False
    def xslt2_transform(xml_string, xslt_path):
        raise NotImplementedError("xslt_helper module could not be loaded. Is Saxon/lxml installed?")


class EDocumentBaseMethods(models.AbstractModel):
    _name = "algebra.base.e_document_base_methods"
    _inherit = ["algebra.ubl.common", "algebra.ubl.json.helper"]
    _description = "Base E-Document Methods"

    def check_document_validity(self):
        self.ensure_one()
        errors = []

        if not self.line_ids:
            errors.append("• The document must have at least one line.")

        if not self.supplier_name:
            errors.append("• Supplier name cannot be empty.")

        if not self.supplier_vkn_tckn:
            errors.append("• Supplier VKN/TCKN cannot be empty.")
        else:
            cleaned = "".join(filter(str.isdigit, self.supplier_vkn_tckn))
            if len(cleaned) not in (10, 11):
                errors.append(f"• Supplier VKN must be 10 digits, TCKN 11 digits (currently: {len(cleaned)} digits).")

        if not self.customer_name:
            errors.append("• Customer name cannot be empty.")

        if not self.customer_vkn_tckn:
            errors.append("• Customer VKN/TCKN cannot be empty.")
        else:
            cleaned = "".join(filter(str.isdigit, self.customer_vkn_tckn))
            if len(cleaned) not in (10, 11):
                errors.append(f"• Customer VKN must be 10 digits, TCKN 11 digits (currently: {len(cleaned)} digits).")

        if not self.profile_id:
            errors.append("• Invoice profile (Profile ID) is not selected.")

        doc_no = (self.id_value or "").strip()
        if not doc_no or doc_no == "/":
            errors.append("• Document number cannot be empty.")

        if errors:
            raise UserError("Document validation errors:\n\n" + "\n".join(errors))

    def _get_service_url(self):
        self.ensure_one()
        config = self.env["ubl21.config.settings"].get_singleton()
        url = config.ubl_service_url
        if not url:
            raise UserError("UBL XML service address (UBL Service URL) is not defined.")
        return url

    def _service_headers(self):
        """
        iber_service_layer'a yapılacak tüm isteklerde kullanılacak header'lar.
        X-Odoo-Database: birden fazla DB varken doğru DB'ye yönlendirme sağlar.
        """
        return {
            "Content-Type": "text/plain",
            "X-Odoo-Database": self.env.cr.dbname,
        }

    def _create_ubl_xml_direct(self, json_payload):
        """
        iber_service_layer aynı Odoo instance'ında kuruluysa HTTP yerine
        doğrudan Python çağrısı yapar — database seçim sorununu ortadan kaldırır.
        """
        try:
            from odoo.addons.iber_service_layer.utils.ubl_tr.ubl_tr import UBLGenerator
            doc_type = json_payload.get("DocumentType", "Invoice")
            builder = self.env["algebra.ubl.factory"].sudo().get_mapper(json_payload)
            document = builder.build_document()
            gen = UBLGenerator()
            if doc_type in ("Despatch", "DespatchAdvice"):
                xml_string, uuid = gen._generate_despatch_ubl_xml_etree(document)
            else:
                xml_string, uuid = gen._generate_invoice_ubl_xml_etree(document)
            xml_bytes = xml_string if isinstance(xml_string, (bytes, bytearray)) else xml_string.encode("utf-8")
            return xml_bytes.decode("utf-8")
        except ImportError:
            return None  # iber_service_layer kurulu değil, HTTP'ye düş

    def _get_xml_from_service(self):
        self.ensure_one()
        self.UUID = str(uuid_engine.uuid4())
        json_payload = self.to_json()

        # Önce aynı instance üzerinde doğrudan çağır
        xml_string = self._create_ubl_xml_direct(json_payload)
        if xml_string:
            _logger.info("UBL XML doğrudan oluşturuldu (local). UUID: %s", self.UUID)
            return xml_string

        # Harici servis — HTTP fallback
        url = self._get_service_url().rstrip("/") + "/create_ubl_xml"
        headers = self._service_headers()
        try:
            response = requests.post(url, headers=headers, data=json.dumps(json_payload))
            if response.status_code == 200:
                _logger.info("UBL XML servisten oluşturuldu. UUID: %s", self.UUID)
                return response.json().get("ubl_xml")
            else:
                raise UserError(
                    _("UBL service returned an error while generating XML (Status: %s):\n%s")
                    % (response.status_code, response.text)
                )
        except requests.exceptions.RequestException as e:
            raise UserError(_("UBL service connection error: %s") % str(e))

    def html_to_pdf_bytes(self, html_string):
        process = subprocess.Popen(
            ["wkhtmltopdf", "-", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = process.communicate(input=html_string.encode("utf-8"))
        if process.returncode != 0:
            raise Exception(f"wkhtmltopdf error: {err.decode('utf-8')}")
        return out

    def get_pdf_data(self):
        self.ensure_one()
        xml_response = self._get_xml_from_service()
        json_payload = self.to_json()
        if not xml_response:
            raise UserError("Could not fetch XML from the service!")
        xslt_path = file_path(self._xslt_path)
        html_content = xslt2_transform(xml_response, xslt_path)
        pdf_bytes = self.html_to_pdf_bytes(html_content)
        self.xml_data = xml_response
        self.json_data = json.dumps(json_payload, indent=4, ensure_ascii=False)
        return base64.b64encode(pdf_bytes)

    def action_preview_pdf(self):
        self.ensure_one()
        pdf_data = self.get_pdf_data()
        filename_base = (self.id_value or "document").strip("/").replace("/", "-") or "document"
        wizard = self.env["l10n_tr.ubl.invoice.pdf.preview.wizard"].create({
            "pdf_data": pdf_data,
            "pdf_filename": f"{filename_base}.pdf",
            "xml_data": self.xml_data,
            "xml_filename": f"{filename_base}.xml",
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("PDF Preview"),
            "res_model": "l10n_tr.ubl.invoice.pdf.preview.wizard",
            "view_mode": "form",
            "views": [(self.env.ref("iber_e_transform.view_ubl_invoice_pdf_preview_wizard_form").id, "form")],
            "res_id": wizard.id,
            "target": "new",
        }

    def to_json(self):
        self.ensure_one()
        return {}
