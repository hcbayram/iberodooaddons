# -*- coding: utf-8 -*-
"""
Hızlı Teknoloji e-Dönüşüm API Entegratörü
API Base: /HizliApi/RestApi/
Auth: username + password HTTP headers (her istekte)

AppType:
  1 = e-Fatura
  2 = e-Arşiv
  3 = e-İrsaliye
  5 = SMM
  6 = e-Makbuz
"""
import logging
import requests

from ..core.hizli_parser import _parse_ubl_xml

from odoo.addons.iber_edonusum.models.integrator_base import IntegratorBase

_logger = logging.getLogger(__name__)

_DOC_TYPE_TO_APPTYPE = {
    "invoice": 1,
    "earchive": 2,
    "despatch": 3,
    "smm": 5,
    "receipt": 6,
}

# DocumentProfile → AppType (belge gönderiminde profil bazlı)
_PROFILE_TO_APPTYPE = {
    "TICARIFATURA": 1,
    "TEMELFATURA": 1,
    "EARSIVFATURA": 2,
    "TEMELIRSALIYE": 3,
    "TICARIIRSALIYE": 3,
}

# PrefixType değerleri
_PREFIXTYPE_MAP = {
    "invoice": 1,
    "earchive": 2,
    "despatch": 3,
}


class HizliIntegrator(IntegratorBase):
    code = "HIZLI"
    name = "Hızlı Teknoloji"

    status_map = {
        "BASARILI": "approved",
        "TAMAMLANDI": "approved",
        "ONAYLANDI": "approved",
        "HATA": "error",
        "BASARISIZ": "error",
        "REDDEDILDI": "rejected",
        "IPTAL": "rejected",
        "BEKLIYOR": "sent",
        "ISLENIYOR": "sent",
        "GONDERILDI": "sent",
        "KUYRUKTA": "sent",
    }

    answer_map = {
        "none": "none",
        "waiting": "waiting",
        "accepted": "accepted",
        "rejected": "rejected",
    }

    def __init__(self, settings: dict):
        self._base_url = (settings.get("url") or "").rstrip("/")
        self._username = settings.get("username") or ""
        self._password = settings.get("password") or ""
        self._secretkey = settings.get("secretkey") or ""
        self._apikey = settings.get("apikey") or ""
        self._token = settings.get("token") or ""
        self._is_test = bool(settings.get("is_test", True))
        self._timeout = int(settings.get("timeout", 30))
        # DB'ye token geri yazabilmek için tutulan referanslar
        self._integ_id = settings.get("_integ_id")
        self._integ_env = settings.get("_integ_env", "test")
        self._settings = settings  # re-login için sakla

    def _current_settings(self) -> dict:
        """Re-login için güncel settings dict'i döner."""
        s = dict(self._settings)
        s["token"] = self._token
        return s

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _auth_headers(self, extra: dict = None) -> dict:
        """Geçerli token varsa Bearer, yoksa username/password header ile auth."""
        token = self._token
        if token:
            h = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        else:
            h = {
                "username": self._username,
                "password": self._password,
                "Content-Type": "application/json",
            }
        if extra:
            h.update(extra)
        return h

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def _is_token_error(self, raw) -> bool:
        """Hızlı API token hatası döndürüp döndürmediğini kontrol eder."""
        if not isinstance(raw, dict):
            return False
        if raw.get("IsSucceeded") is False:
            msg = str(raw.get("Message") or "").lower()
            return "token" in msg or "giriş" in msg
        return False

    def _get(self, path: str, params: dict = None, extra_headers: dict = None, _retry=True, _raw_bytes=False) -> dict:
        try:
            resp = requests.get(
                self._url(path),
                headers=self._auth_headers(extra_headers),
                params=params or {},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            if _raw_bytes:
                # İlk 1 byte JSON mi kontrol et (token hatası olabilir)
                if resp.content[:1] == b"{":
                    try:
                        raw = resp.json()
                        if _retry and self._is_token_error(raw):
                            _logger.info("Token geçersiz (_raw_bytes), yeniden login yapılıyor...")
                            tr = self.get_token(self._current_settings())
                            if tr.get("ok"):
                                return self._get(path, params, extra_headers, _retry=False, _raw_bytes=True)
                        return {"ok": True, "raw": raw}
                    except Exception:
                        pass
                return {"ok": True, "raw": resp.content, "content_type": resp.headers.get("Content-Type", "")}
            raw = resp.json()
            if _retry and self._is_token_error(raw):
                _logger.info("Token geçersiz, yeniden login yapılıyor...")
                tr = self.get_token(self._current_settings())
                if tr.get("ok"):
                    return self._get(path, params, extra_headers, _retry=False)
            return {"ok": True, "raw": raw, "status_code": resp.status_code}
        except requests.HTTPError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _post(self, path: str, payload, extra_headers: dict = None, _retry=True) -> dict:
        try:
            resp = requests.post(
                self._url(path),
                headers=self._auth_headers(extra_headers),
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            try:
                raw = resp.json()
                if _retry and self._is_token_error(raw):
                    _logger.info("Token geçersiz (POST), yeniden login yapılıyor...")
                    tr = self.get_token(self._current_settings())
                    if tr.get("ok"):
                        return self._post(path, payload, extra_headers, _retry=False)
                return {"ok": True, "raw": raw, "status_code": resp.status_code}
            except Exception:
                return {"ok": True, "raw": resp.text, "status_code": resp.status_code}
        except requests.HTTPError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _extract_first(self, raw):
        """API yanıtından ilk kayıt objesini döner."""
        if isinstance(raw, list):
            return raw[0] if raw else {}
        if isinstance(raw, dict):
            data = raw.get("Data") or raw.get("data") or raw.get("Documents") or []
            if isinstance(data, list):
                return data[0] if data else raw
            return raw
        return {}

    def _extract_list(self, raw) -> list:
        """API yanıtından kayıt listesini döner."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            for key in ("Data", "data", "Documents", "documents", "Items", "items"):
                val = raw.get(key)
                if isinstance(val, list):
                    return val
        return []

    # ------------------------------------------------------------------
    # IntegratorBase implementasyonları
    # ------------------------------------------------------------------

    def get_token(self, settings: dict) -> dict:
        """
        Hızlı 2 adımlı login:
        1. POST /UtilEncrypt  → kripto kullanıcı adı/şifre
        2. POST /Login        → Bearer token
        Token başarıyla alınırsa edn.integrator kaydına geri yazılır.
        """
        base_url = (settings.get("url") or "").rstrip("/")
        username = settings.get("username") or ""
        password = settings.get("password") or ""
        secretkey = settings.get("secretkey") or ""
        apikey = settings.get("apikey") or ""
        timeout = int(settings.get("timeout", 30))

        # --- Adım 1: Şifrele ---
        try:
            r1 = requests.post(
                f"{base_url}/UtilEncrypt",
                json={"secretKey": secretkey, "username": username, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            r1.raise_for_status()
            enc = r1.json()
            if isinstance(enc, list):
                enc = enc[0] if enc else {}
        except Exception as e:
            return {"ok": False, "error": f"UtilEncrypt hatası: {e}"}

        if not enc.get("IsSucceeded"):
            return {"ok": False, "error": f"UtilEncrypt başarısız: {enc.get('Message')}"}

        crypto_username = enc.get("username") or enc.get("Username") or ""
        crypto_password = enc.get("password") or enc.get("Password") or ""

        # --- Adım 2: Login ---
        try:
            r2 = requests.post(
                f"{base_url}/Login",
                json={"apiKey": apikey, "username": crypto_username, "password": crypto_password},
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            r2.raise_for_status()
            login = r2.json()
            if isinstance(login, list):
                login = login[0] if login else {}
        except Exception as e:
            return {"ok": False, "error": f"Login hatası: {e}"}

        if not login.get("IsSucceeded"):
            return {"ok": False, "error": f"Login başarısız: {login.get('Message')}"}

        token = login.get("Token") or ""
        self._token = token

        # Token'ı edn.integrator kaydına geri yaz
        self._save_token(token, settings)

        return {"ok": True, "token": token, "raw": login}

    def _save_token(self, token: str, settings: dict):
        """Sadece in-memory token günceller. DB yazımı _get_integrator_client'ta yapılır."""
        self._token = token

    def send_document(self, document_data: dict) -> dict:
        """
        Belgeyi Hızlı /SendDocument endpoint'ine gönderir.
        XmlContent string olarak gönderilir (base64 değil).
        """
        profile = (document_data.get("DocumentProfile") or "").upper()
        doc_type = (document_data.get("DocumentType") or "").lower()

        app_type = _PROFILE_TO_APPTYPE.get(profile) or _DOC_TYPE_TO_APPTYPE.get(doc_type, 1)

        json_payload = document_data.get("JsonPayload") or {}
        doc_date = json_payload.get("IssueDate") or json_payload.get("document_date") or ""
        doc_id = json_payload.get("ID") or json_payload.get("document_no") or ""

        payload = [{
            "AppType": app_type,
            "DestinationIdentifier": document_data.get("CustomerRegisterNumber") or "",
            "DestinationUrn": document_data.get("ReceiverAlias") or "",
            "SourceUrn": document_data.get("SenderAlias") or "",
            "DocumentDate": doc_date,
            "DocumentId": doc_id,
            "DocumentUUID": document_data.get("UUID") or "",
            "IsDraft": False,
            "IsDraftSend": False,
            "UpdateDocument": False,
            "XmlContent": document_data.get("File") or "",
        }]

        result = self._post("SendDocument", payload)
        if not result.get("ok"):
            return result

        item = self._extract_first(result.get("raw"))
        success = bool(
            item.get("IsSucceed") or item.get("isSucceed") or
            item.get("Success") or item.get("success")
        ) if isinstance(item, dict) else True

        return {
            "ok": success,
            "uuid": document_data.get("UUID"),
            "raw": item,
            "error": (item.get("Message") or item.get("message")) if not success else None,
        }

    def get_incoming_documents(self, filters: dict) -> dict:
        """
        Gelen belgeleri listeler.
        GET /GetDocumentList?AppType=X&DateType=IssueDate&StartDate=...&EndDate=...
        """
        doc_type = filters.get("doc_type", "invoice")
        app_type = _DOC_TYPE_TO_APPTYPE.get(doc_type, 1)

        # Tarih: startCreateDate/endCreateDate (oluşturma tarihi) veya startDate/endDate (fatura tarihi)
        start_date = (
            filters.get("startDate") or filters.get("startCreateDate") or
            filters.get("start_date") or ""
        )
        end_date = (
            filters.get("endDate") or filters.get("endCreateDate") or
            filters.get("end_date") or ""
        )
        params = {
            "AppType": app_type,
            "DateType": "IssueDate",
            "StartDate": start_date,
            "EndDate": end_date,
            "IsNew": str(filters.get("is_new", False)).lower(),
            "IsExport": "false",
            "TakenFromEntegrator": "ALL",
            "IsDraft": "false",
        }
        result = self._get("GetDocumentList", params)
        if not result.get("ok"):
            return result

        raw = result.get("raw")
        _logger.info("GetDocumentList ham yanıt tipi: %s", type(raw).__name__)
        if isinstance(raw, dict):
            _logger.info("Ham yanıt keys: %s | IsSucceeded: %s | Message: %s",
                         list(raw.keys()), raw.get("IsSucceeded"), raw.get("Message"))
            docs = raw.get("documents") or raw.get("Documents")
            _logger.info("documents alanı tipi: %s, uzunluk: %s",
                         type(docs).__name__, len(docs) if isinstance(docs, list) else "N/A")
            if isinstance(docs, list) and docs:
                _logger.info("İlk ham item keys: %s", list(docs[0].keys()) if isinstance(docs[0], dict) else docs[0])
        elif isinstance(raw, list):
            _logger.info("Liste uzunluğu: %d", len(raw))
            if raw:
                _logger.info("İlk ham item keys: %s", list(raw[0].keys()) if isinstance(raw[0], dict) else raw[0])

        items = self._extract_list(raw)
        documents = []
        for item in items:
            if not isinstance(item, dict):
                continue
            uuid = item.get("UUID") or item.get("DocumentUUID") or item.get("Uuid") or ""
            doc_no = item.get("DocumentId") or item.get("DocumentNo") or ""
            issue_date = item.get("IssueDate") or item.get("DocumentDate") or ""
            # Gelen faturada: Target = alıcı (biz), Source = gönderici (tedarikçi)
            receiver_vkn = item.get("TargetIdentifier") or ""
            receiver_name = item.get("TargetTitle") or ""
            receiver_alias = item.get("TargetAlias") or ""
            sender_alias = item.get("SourceAlias") or ""
            documents.append({
                # _map_incoming_invoice'ın beklediği key'ler
                "id": uuid,
                "uuid": uuid,
                "documentNumber": doc_no,
                "issueDate": issue_date,
                "senderIdentifier": "",   # liste endpoint'inde gelmiyor
                "senderTitle": "",
                "receiverIdentifier": receiver_vkn,
                "receiverTitle": receiver_name,
                "documentStatus": item.get("Status") or "",
                "documentAnswer": item.get("AppResGibResult") or "",
                "profileId": item.get("ProfileId") or "",
                # Hızlı özgün alanlar
                "sender_alias": sender_alias,
                "receiver_vkn": receiver_vkn,
                "receiver_alias": receiver_alias,
                "raw": item,
            })

        return {"ok": True, "documents": documents, "raw": result.get("raw")}

    def check_document_status(self, uuid: str) -> dict:
        """
        UUID ile belge durumunu sorgular.
        POST /GetDocumentListGUID (GET'ten daha esnek, birden fazla UUID destekler)
        """
        return self._query_by_uuid(uuid, app_type=1)

    def get_outgoing_document(self, uuid: str, doc_type: str = "invoice") -> dict:
        """Giden belgenin durumunu ve bilgilerini sorgular."""
        app_type = _DOC_TYPE_TO_APPTYPE.get(doc_type, 1)
        result = self._query_by_uuid(uuid, app_type=app_type)
        if not result.get("ok"):
            return result

        item = result.get("raw") or {}
        status_raw = (item.get("Status") or item.get("DocumentStatus") or "").upper()
        return {
            "ok": True,
            "status": status_raw,
            "uuid": uuid,
            "envelope_id": item.get("EnvelopeId") or item.get("ZarfId") or "",
            "response_date": item.get("ResponseDate") or item.get("CevapTarihi") or "",
            "response_note": item.get("ResponseDescription") or item.get("CevapAciklama") or "",
            "invoice_number": item.get("DocumentId") or item.get("DocumentNo") or "",
            "raw": item,
        }

    def _query_by_uuid(self, uuid: str, app_type: int = 1) -> dict:
        """
        POST /GetDocumentListGUID — tek veya çoklu UUID sorgulama.
        """
        payload = {"AppType": app_type, "GUIDList": [uuid]}
        result = self._post("GetDocumentListGUID", payload)
        if not result.get("ok"):
            return result
        item = self._extract_first(result.get("raw"))
        return {"ok": True, "raw": item}

    def mark_documents_received(self, uuids: list, doc_type: str = "invoice") -> dict:
        """
        POST /SetTakenFromEntegrator — belgelerin entegratörden alındığını işaretler.
        Gelen belge senkronizasyonu sonrası çağrılır.
        """
        app_type = _DOC_TYPE_TO_APPTYPE.get(doc_type, 1)
        payload = {"AppType": app_type, "GUIDList": uuids}
        return self._post("SetTakenFromEntegrator", payload)

    def send_application_response(
        self,
        uuid: str,
        doc_id: str,
        doc_date: str,
        response_code: str,
        response_description: str = "",
        doc_type: str = "invoice",
    ) -> dict:
        """
        POST /SendApplicationResponse — gelen faturaya kabul/red yanıtı gönderir.
        response_code: "KABUL" veya "RED"
        """
        app_type = _DOC_TYPE_TO_APPTYPE.get(doc_type, 1)
        payload = {
            "AppType": app_type,
            "Documents": [{
                "DocumentDate": doc_date,
                "DocumentId": doc_id,
                "DocumentUUID": uuid,
            }],
            "ResponseCode": response_code.upper(),
            "ResponseDescription": response_description,
        }
        return self._post("SendApplicationResponse", payload)

    def get_series(self, document_type: str = "invoice") -> dict:
        """
        GET /PrefixCodeList?PrefixType=X — seri kodu listesi.
        """
        prefix_type = _PREFIXTYPE_MAP.get(document_type, 1)
        result = self._get("PrefixCodeList", {"PrefixType": prefix_type})
        if not result.get("ok"):
            return result

        raw = result.get("raw") or []
        items = raw if isinstance(raw, list) else self._extract_list(raw)
        series = []
        for item in items:
            if isinstance(item, dict):
                series.append({
                    "prefix": (
                        item.get("Prefix") or item.get("prefix") or
                        item.get("SeriesPrefix") or item.get("PrefixCode") or ""
                    ),
                    "description": item.get("Description") or item.get("description") or "",
                })
            elif isinstance(item, str):
                series.append({"prefix": item, "description": ""})

        return {"ok": True, "raw": series}

    def get_invoice_lines(self, uuid: str) -> dict:
        """XML çekip UBL-TR satırlarını parse eder. action_fetch_single_incoming için."""
        xml_result = self._get_document_file(uuid, "invoice", tur="XML")
        if not xml_result.get("ok"):
            return xml_result
        xml_bytes = xml_result.get("pdf_bytes") or b""
        xml_text = xml_result.get("content") or (xml_bytes.decode("utf-8", errors="replace") if xml_bytes else "")
        if not xml_text:
            return {"ok": False, "error": "XML içeriği boş"}
        try:
            return {"ok": True, "raw": _parse_ubl_xml(xml_text)}
        except Exception as ex:
            return {"ok": False, "error": f"XML parse hatası: {ex}"}

    def get_incoming_document_pdf(self, uuid: str, doc_type: str = "invoice") -> dict:
        """GET /GetDocumentFile?Tur=PDF — gelen belge PDF'i."""
        return self._get_document_file(uuid, doc_type, tur="PDF")

    def get_outgoing_document_pdf(self, uuid: str, doc_type: str = "invoice") -> dict:
        """GET /GetDocumentFile?Tur=PDF — giden belge PDF'i."""
        return self._get_document_file(uuid, doc_type, tur="PDF")

    def get_incoming_document_xml(self, uuid: str, doc_type: str = "invoice") -> dict:
        """GET /GetDocumentFile?Tur=XML — gelen belge XML'i."""
        return self._get_document_file(uuid, doc_type, tur="XML")

    def _get_document_file(self, uuid: str, doc_type: str, tur: str = "PDF") -> dict:
        """
        GET /GetDocumentFile
        Not: Postman koleksiyonunda IssueDate header'ı var ancak opsiyonel.
        """
        import base64 as _b64
        app_type = _DOC_TYPE_TO_APPTYPE.get(doc_type, 1)
        params = {"AppType": app_type, "Uuid": uuid, "Tur": tur, "IsDraft": "false"}
        result = self._get("GetDocumentFile", params, _raw_bytes=True)  # token retry dahil
        if not result.get("ok"):
            return result
        raw = result.get("raw")
        if isinstance(raw, dict):
            _logger.info("GetDocumentFile JSON keys: %s | IsSucceeded: %s", list(raw.keys()), raw.get("IsSucceeded"))
            if raw.get("IsSucceeded") is False:
                return {"ok": False, "error": raw.get("Message") or "Dosya alınamadı"}
            b64 = (raw.get("DocumentFile") or raw.get("Data") or raw.get("data") or
                   raw.get("Content") or raw.get("FileContent") or "")
            if b64:
                try:
                    return {"ok": True, "pdf_bytes": _b64.b64decode(b64)}
                except Exception as ex:
                    return {"ok": False, "error": f"Base64 decode hatası: {ex}"}
            return {"ok": False, "error": "JSON yanıtında dosya içeriği bulunamadı"}
        # Binary yanıt (direkt PDF/XML bytes)
        if isinstance(raw, (bytes, bytearray)):
            if raw[:4] == b"%PDF" or tur == "PDF":
                return {"ok": True, "pdf_bytes": raw}
            return {"ok": True, "content": raw.decode("utf-8", errors="replace"), "pdf_bytes": None}
        return {"ok": False, "error": "Beklenmeyen yanıt formatı"}
