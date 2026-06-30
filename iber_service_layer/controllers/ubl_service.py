import json
import base64
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class IberUBLService(http.Controller):
    """
    İberoDoo UBL Service Layer — REST API Controller

    Her endpoint hem yeni (/iber_service_layer/) hem de eski (/algebra_service_layer/)
    rotaları aynı anda dinler. Geriye dönük uyumluluk için.
    """

    def _get_ubl_generator(self):
        """UBLGenerator'ı lazy import ile döner."""
        from ..utils.ubl_tr.ubl_tr import UBLGenerator
        return UBLGenerator()

    @http.route(
        [
            "/iber_service_layer/create_ubl_xml",
            "/algebra_service_layer/create_ubl_xml",
        ],
        type="http",
        auth="public",
        csrf=False,
        methods=["POST"],
    )
    def create_ubl_xml(self):
        """
        JSON payload'dan UBL-TR 2.1 XML oluşturur ve döndürür.

        Request (JSON):
            {
                "DocumentType": "Invoice" | "DespatchAdvice",
                "Header": { "ProfileID": "TEMELFATURA", ... },
                "Company": { ... },
                "Customer": { ... },
                "Lines": [ ... ],
                ...
            }

        Response (JSON):
            {
                "status": "ok",
                "document_type": "Invoice",
                "uuid": "...",
                "ubl_xml": "<Invoice>...</Invoice>",
                "ubl_xml_base64": "..."
            }
        """
        raw = request.httprequest.data or b"{}"
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            return request.make_response(
                json.dumps({"status": "error", "message": f"Invalid JSON: {str(e)}"}),
                status=400,
                headers=[("Content-Type", "application/json")],
            )

        doc_type = (payload.get("DocumentType") or "Invoice").strip()
        if doc_type not in ("Invoice", "Despatch", "DespatchAdvice", "PurchaseCreditNote"):
            return request.make_response(
                json.dumps({"status": "error", "message": f"Unsupported DocumentType: {doc_type}"}),
                status=400,
                headers=[("Content-Type", "application/json")],
            )

        try:
            builder = request.env["algebra.ubl.factory"].sudo().get_mapper(payload)
            document = builder.build_document()

            gen = self._get_ubl_generator()
            if doc_type in ("Despatch", "DespatchAdvice"):
                xml_string, uuid = gen._generate_despatch_ubl_xml_etree(document)
            else:
                xml_string, uuid = gen._generate_invoice_ubl_xml_etree(document)

            xml_bytes = (
                xml_string
                if isinstance(xml_string, (bytes, bytearray))
                else xml_string.encode("utf-8")
            )
            b64 = base64.b64encode(xml_bytes).decode()

            resp = {
                "status": "ok",
                "document_type": doc_type,
                "uuid": uuid,
                "ubl_xml": xml_bytes.decode("utf-8"),
                "ubl_xml_base64": b64,
            }
            _logger.info("UBL XML oluşturuldu — type=%s uuid=%s", doc_type, uuid)

        except Exception as e:
            _logger.error("UBL XML oluşturma hatası: %s", str(e), exc_info=True)
            return request.make_response(
                json.dumps({"status": "error", "message": f"XML oluşturulurken hata: {str(e)}"}),
                status=500,
                headers=[("Content-Type", "application/json")],
            )

        return request.make_response(
            json.dumps(resp),
            headers=[("Content-Type", "application/json")],
        )

    @http.route(
        [
            "/iber_service_layer/send_ubl_xml",
            "/algebra_service_layer/send_ubl_xml",
        ],
        type="http",
        auth="public",
        csrf=False,
        methods=["POST"],
    )
    def send_ubl_xml(self):
        """
        Oluşturulan UBL XML'ini entegratöre (NES, Uyumsoft, Foriba vb.) gönderir.
        """
        raw = request.httprequest.data or b"{}"
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            return request.make_response(
                json.dumps({"status": "error", "message": f"Invalid JSON: {str(e)}"}),
                status=400,
                headers=[("Content-Type", "application/json")],
            )

        ubl_xml = payload.get("File")
        if not ubl_xml:
            return request.make_response(
                json.dumps({"status": "error", "message": "Missing 'File' field (UBL XML)"}),
                status=400,
                headers=[("Content-Type", "application/json")],
            )

        try:
            if "edn.document.manager" in request.env:
                resp = request.env["edn.document.manager"].sudo().send_document(payload)
            else:
                _logger.warning(
                    "edn.document.manager modeli bulunamadı — entegratör gönderimi atlandı."
                )
                resp = {
                    "status": "pending",
                    "message": (
                        "UBL XML oluşturuldu fakat entegratör gönderim modeli "
                        "(edn.document.manager) kurulu değil."
                    ),
                    "uuid": payload.get("UUID", ""),
                }
        except Exception as e:
            _logger.error("Entegratör gönderim hatası: %s", str(e), exc_info=True)
            return request.make_response(
                json.dumps({"status": "error", "message": f"Belge gönderilirken hata: {str(e)}"}),
                status=500,
                headers=[("Content-Type", "application/json")],
            )

        return request.make_response(
            json.dumps(resp),
            headers=[("Content-Type", "application/json")],
        )

    @http.route(
        "/iber_service_layer/ping",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def ping(self):
        """Servisin ayakta olduğunu test etmek için basit endpoint."""
        return request.make_response(
            json.dumps({"status": "ok", "service": "iber_service_layer"}),
            headers=[("Content-Type", "application/json")],
        )
