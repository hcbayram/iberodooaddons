import json
import logging
from datetime import datetime, timedelta, timezone
from odoo import models, api
from .integrator_factory import get_integrator, list_integrators

_logger = logging.getLogger(__name__)


class EDNDocumentManager(models.Model):
    """
    E-Dönüşüm belge gönderim/alım servisi.
    iber_service_layer'ın send_ubl_xml endpoint'i bu modeli çağırır.
    """
    _name = "edn.document.manager"
    _description = "e-Transformation Document Management"
    _log_access = False  # kayıt oluşturmuyor

    # ------------------------------------------------------------------
    # Yardımcı
    # ------------------------------------------------------------------
    @api.model
    def _get_integrator_client(self, integrator_code: str):
        # NOT: bu metod çoğu yerde .sudo() edilmiş bir recordset üzerinden
        # çağrılıyor (ir.rule bypass edilir) — company_id filtresi bu yüzden
        # burada açıkça uygulanıyor; aksi halde başka şirketin entegratör
        # credential'ları (kullanıcı adı/şifre) yanlışlıkla kullanılabilir.
        integ = self.env["edn.integrator"].search(
            [
                ("code", "=", integrator_code),
                ("active", "=", True),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        if not integ:
            raise ValueError(f"Integrator not found or not active: {integrator_code}")
        settings = self._make_settings(integ)
        client = get_integrator(integrator_code, settings)
        # Token yoksa veya süresi dolmuşsa yeniden login yap
        _logger.info("Token kontrolü: mevcut token=%s, expiry=%s",
                     bool(settings.get("token")), settings.get("token_expiry"))
        if self._token_expired(settings):
            token_result = client.get_token(settings)
            _logger.info("get_token sonucu: ok=%s, token_var=%s, hata=%s",
                         token_result.get("ok"), bool(token_result.get("token")), token_result.get("error"))
            if not token_result.get("ok"):
                _logger.warning(
                    "Entegratör %s token alınamadı: %s",
                    integrator_code, token_result.get("error")
                )
            else:
                self._save_integrator_token(integ, settings, token_result)
        _logger.info("client._token var mı: %s", bool(getattr(client, "_token", None)))
        return client

    @api.model
    def _save_integrator_token(self, integ, settings, token_result):
        """Token ve expiry'yi doğrudan env üzerinden yazar."""
        token = token_result.get("token") or ""
        if not token:
            return
        is_test = settings.get("is_test", True)
        token_field = "test_token" if is_test else "token"
        expiry = datetime.utcnow() + timedelta(hours=23, minutes=50)
        vals = {token_field: token}
        # Entegratör kodu bazlı expiry alanı (her entegratör addon kendi alanını ekler)
        code = integ.code or ""
        expiry_field = f"{code.lower()}_{'test_' if is_test else ''}token_expiry"
        if expiry_field in integ._fields:
            vals[expiry_field] = expiry
        integ.write(vals)

    @api.model
    def _token_expired(self, settings: dict) -> bool:
        """Token yoksa veya geçerlilik süresi dolmuşsa True döner (5 dk erken)."""
        token = settings.get("token")
        if not token:
            return True
        expiry = settings.get("token_expiry")
        if not expiry:
            return True
        # Odoo datetime alanı naive UTC olarak saklar
        now = datetime.utcnow()
        margin = timedelta(minutes=5)
        if isinstance(expiry, datetime):
            return now >= (expiry - margin)
        return True

    @api.model
    def _make_settings(self, integ):
        extra = {}
        if integ.extra:
            try:
                extra = json.loads(integ.extra)
            except Exception:
                pass
        is_test = bool(integ.is_test)
        if is_test:
            url = integ.test_base_url or integ.base_url or ""
            username = integ.test_username or integ.username or ""
            password = integ.test_password or integ.password or ""
            apikey = integ.test_apikey or integ.apikey or ""
            token = integ.test_token or ""
            env = "test"
        else:
            url = integ.base_url or ""
            username = integ.username or ""
            password = integ.password or ""
            apikey = integ.apikey or ""
            token = integ.token or ""
            env = "prod"
        return {
            "url": url,
            "username": username,
            "password": password,
            "apikey": apikey,
            "token": token,
            "token_expiry": None,
            "secretkey": "",
            "is_test": is_test,
            "_integ_id": integ.id,
            "_integ_env": env,
            **extra,
        }

    def _write_log(self, *, integrator, document_no=None, uuid=None,
                   jsonpayload=None, xmlpayload=None, payload=None, result, status):
        # sudo(): edn.log oluşturma yalnızca base.group_system (Ayarlar/
        # Yönetici) grubuna açık — bu, sıradan bir iş kullanıcısının
        # "Entegratörden Faturaları Getir" gibi günlük işlemlerde
        # AccessError almasına yol açıyordu (log tutmak, tetikleyen
        # kullanıcının yetkisine bağlı olmamalı).
        self.env["edn.log"].sudo().create({
            "integrator": integrator,
            "document_no": document_no,
            "uuid": uuid,
            "jsonpayload": json.dumps(jsonpayload, ensure_ascii=False, indent=2) if jsonpayload else None,
            "xmlpayload": xmlpayload,
            "payload": json.dumps(payload, ensure_ascii=False, indent=2) if isinstance(payload, dict) else payload,
            "result": json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, dict) else result,
            "status": status,
        })

    # ------------------------------------------------------------------
    # Belge Gönder (iber_service_layer → send_ubl_xml endpoint'i bu metodu çağırır)
    # ------------------------------------------------------------------
    @api.model
    def send_document(self, document_data: dict):
        """
        UBL XML belgesini entegratöre gönderir.

        document_data yapısı:
            {
                "IntegratorInfo": {"IntegratorCode": "NES", "test_mode": true, ...},
                "DocumentType": "Invoice",
                "DocumentProfile": "TEMELFATURA",
                "File": "<Invoice>...</Invoice>",
                "UUID": "...",
                "SenderAlias": "...",
                "ReceiverAlias": "...",
                "CustomerRegisterNumber": "...",
                "JsonPayload": {...}
            }
        """
        integrator_code = (
            document_data.get("IntegratorInfo", {}).get("IntegratorCode")
            if isinstance(document_data, dict) else None
        )
        if not integrator_code:
            raise ValueError("IntegratorInfo.IntegratorCode is missing.")

        client = self._get_integrator_client(integrator_code)
        result = client.send_document(document_data)

        status = "success" if result.get("ok") else "error"
        self._write_log(
            integrator=integrator_code,
            uuid=document_data.get("UUID"),
            jsonpayload=document_data.get("JsonPayload"),
            xmlpayload=document_data.get("File"),
            payload=document_data,
            result=result,
            status=status,
        )
        return result

    # ------------------------------------------------------------------
    # Belge Durum Sorgula
    # ------------------------------------------------------------------
    @api.model
    def check_document_status(self, integrator_code: str, uuid: str):
        client = self._get_integrator_client(integrator_code)
        result = client.check_document_status(uuid)
        self._write_log(
            integrator=integrator_code,
            uuid=uuid,
            payload=uuid,
            result=result,
            status="success" if result.get("ok") else "error",
        )
        return result

    # ------------------------------------------------------------------
    # Gelen Belgeler
    # ------------------------------------------------------------------
    @api.model
    def get_incoming_documents(self, integrator_code: str, filters: dict = None, client=None):
        if client is None:
            client = self._get_integrator_client(integrator_code)
        result = client.get_incoming_documents(filters or {})
        self._write_log(
            integrator=integrator_code,
            payload=filters or {},
            result=result,
            status="success" if result.get("ok") else "error",
        )
        return result

    # ------------------------------------------------------------------
    # PDF İndirme
    # ------------------------------------------------------------------
    @api.model
    def get_incoming_document_pdf(self, integrator_code: str, uuid: str, doc_type: str = "invoice"):
        """Gelen belge PDF'ini entegratörden indirir. {"ok", "pdf_bytes", "error"}"""
        client = self._get_integrator_client(integrator_code)
        return client.get_incoming_document_pdf(uuid, doc_type=doc_type)

    @api.model
    def get_outgoing_document_pdf(self, integrator_code: str, uuid: str, doc_type: str = "invoice"):
        """Giden belge PDF'ini entegratörden indirir. {"ok", "pdf_bytes", "error"}"""
        client = self._get_integrator_client(integrator_code)
        return client.get_outgoing_document_pdf(uuid, doc_type=doc_type)

    # Geriye dönük uyumluluk aliasları
    @api.model
    def get_incoming_invoice_pdf(self, integrator_code: str, uuid: str):
        return self.get_incoming_document_pdf(integrator_code, uuid, doc_type="invoice")

    @api.model
    def get_outgoing_invoice_pdf(self, integrator_code: str, uuid: str):
        return self.get_outgoing_document_pdf(integrator_code, uuid, doc_type="invoice")

    # ------------------------------------------------------------------
    # Kayıtlı Entegratörler
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Giden Fatura Durum Sorgula (NES /einvoice/v1/outgoing/invoices/{uuid})
    # ------------------------------------------------------------------
    @api.model
    def get_outgoing_invoice_status(self, integrator_code: str, uuid: str):
        client = self._get_integrator_client(integrator_code)
        result = client.get_outgoing_invoice(uuid)
        self._write_log(
            integrator=integrator_code,
            uuid=uuid,
            payload={"action": "get_outgoing_invoice_status", "uuid": uuid},
            result=result,
            status="success" if result.get("ok") else "error",
        )
        return result

    @api.model
    def available_integrators(self):
        return list_integrators()

    @api.model
    def fetch_and_sync_series(self, integrator_code: str) -> dict:
        """
        Entegratörden tüm seri tiplerini çekip edn.invoice.series tablosuna kaydeder.
        Mevcut kayıtları günceller, yenilerini ekler.
        """
        integ = self.env["edn.integrator"].search(
            [
                ("code", "=", integrator_code),
                ("active", "=", True),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        if not integ:
            raise UserError(f"Integrator not found: {integrator_code}")

        client = self._get_integrator_client(integrator_code)
        synced = 0
        errors = []

        for doc_type in ("invoice", "earchive", "despatch"):
            result = client.get_series(document_type=doc_type)
            if not result.get("ok"):
                errors.append(f"{doc_type}: {result.get('error','?')}")
                continue

            series_list = result.get("raw") or []
            if not isinstance(series_list, list):
                continue

            for item in series_list:
                # NES yanıtı: {"prefix": "IBR", ...} veya {"seriesPrefix": "IBR", ...}
                prefix = (
                    item.get("prefix")
                    or item.get("seriesPrefix")
                    or item.get("serie")
                    or ""
                ).strip().upper()

                if not prefix:
                    continue

                description = (
                    item.get("description")
                    or item.get("name")
                    or item.get("title")
                    or ""
                )

                existing = self.env["edn.invoice.series"].search([
                    ("integrator_id", "=", integ.id),
                    ("prefix", "=", prefix),
                    ("document_type", "=", doc_type),
                ], limit=1)

                vals = {
                    "integrator_id": integ.id,
                    "prefix": prefix,
                    "document_type": doc_type,
                    "description": description,
                    "raw_data": json.dumps(item, ensure_ascii=False),
                }

                if existing:
                    existing.write(vals)
                else:
                    self.env["edn.invoice.series"].create(vals)

                synced += 1

        if errors:
            return {
                "ok": False,
                "synced": synced,
                "error": "Bazı seri tipleri çekilemedi:\n" + "\n".join(errors),
            }

        return {"ok": True, "synced": synced, "error": None}
