# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod


class IntegratorBase(ABC):
    """
    Tüm entegratörlerin implement etmesi gereken temel arayüz.

    Zorunlu metodlar (abstract):
        get_token, send_document, get_incoming_documents, check_document_status

    Opsiyonel metodlar (default: NotImplementedError):
        get_invoice_lines, get_despatch_lines,
        get_outgoing_document, get_series,
        get_incoming_document_pdf, get_outgoing_document_pdf

    Durum çevirisi:
        Her entegratör sınıfı kendi status_map ve answer_map'ini tanımlar.
        translate_status() ve translate_answer() bu map'leri kullanır.
    """

    code: str = None
    name: str = None

    # Entegratör ham durum string'i → gib_status değeri
    # Örn: {"APPROVED": "approved", "REJECTED": "rejected", ...}
    status_map: dict = {}

    # Entegratör ham cevap string'i → iç cevap değeri
    # Örn: {"accepted": "accepted", "rejected": "rejected", ...}
    answer_map: dict = {}

    def __init__(self, settings: dict):
        """
        :param settings: {
            "url": str, "apikey": str, "token": str,
            "username": str, "password": str, "is_test": bool,
            ...entegratöre özgü ek alanlar...
        }
        """
        self.settings = settings or {}

    # ------------------------------------------------------------------ #
    #  Durum Çevirisi                                                      #
    # ------------------------------------------------------------------ #

    def translate_status(self, raw_status: str, default: str = "sent") -> str:
        """Ham entegratör durumunu gib_status değerine çevirir."""
        if not raw_status:
            return default
        return self.status_map.get(raw_status.strip().upper(), default)

    def translate_answer(self, raw_answer: str, default: str = "none") -> str:
        """Ham entegratör cevabını iç cevap değerine çevirir."""
        if not raw_answer:
            return default
        return self.answer_map.get(raw_answer.strip().lower(), default)

    # ------------------------------------------------------------------ #
    #  Zorunlu Metodlar                                                    #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_token(self) -> dict:
        """
        Kimlik doğrulama / token alma.
        Dönüş: {"ok": bool, "token": str, "raw": dict, "error": str}
        """

    @abstractmethod
    def send_document(self, document: dict) -> dict:
        """
        Belge gönderimi (fatura, irsaliye vb.).
        :param document: {"xml": str, "uuid": str, "doc_type": str, ...}
        Dönüş: {"ok": bool, "raw": dict, "error": str, "status_code": int}
        """

    @abstractmethod
    def get_incoming_documents(self, filters: dict | None = None) -> dict:
        """
        Gelen belgeleri listeler.
        :param filters: {
            "document_type": "invoice"|"despatch",
            "startCreateDate": "YYYY-MM-DD",
            "endCreateDate":   "YYYY-MM-DD",
            "include_lines": bool,
        }
        Dönüş: {"ok": bool, "raw": dict, "error": str}
                raw içinde "data" veya "items" listesi beklenir.
        """

    @abstractmethod
    def check_document_status(self, uuid: str) -> dict:
        """
        Belge durum kontrolü (UUID ile).
        Dönüş: {"ok": bool, "status": str, "raw": dict, "error": str}
        """

    # ------------------------------------------------------------------ #
    #  Opsiyonel Metodlar                                                  #
    # ------------------------------------------------------------------ #

    def get_invoice_lines(self, uuid: str) -> dict:
        """
        Gelen fatura kalemlerini/XML'ini UUID ile çeker.
        Dönüş: {"ok": bool, "raw": dict, "error": str}
                raw: {"header": dict, "xml_clean": str, "documentTotals": dict, ...}
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} get_invoice_lines() metodunu implement etmedi."
        )

    def get_despatch_lines(self, uuid: str) -> dict:
        """
        Gelen irsaliye kalemlerini/XML'ini UUID ile çeker.
        Dönüş: {"ok": bool, "raw": dict, "error": str}
                raw: {"header": dict, "xml_clean": str, ...}
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} get_despatch_lines() metodunu implement etmedi."
        )

    def get_outgoing_document(self, uuid: str, doc_type: str = "invoice") -> dict:
        """
        Giden belgenin entegratördeki güncel durumunu çeker.
        :param doc_type: "invoice" | "earchive" | "despatch"
        Dönüş: {
            "ok": bool, "status": str, "raw": dict, "error": str,
            "envelope_id": str, "invoice_number": str,
            "response_date": str, "response_note": str,
        }
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} get_outgoing_document() metodunu implement etmedi."
        )

    def get_series(self, document_type: str = "invoice") -> dict:
        """
        Entegratöre kayıtlı seri/prefix listesini çeker.
        :param document_type: "invoice" | "earchive" | "despatch"
        Dönüş: {"ok": bool, "raw": list[dict], "error": str}
                Her eleman: {"prefix": str, "type": str, ...}
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} get_series() metodunu implement etmedi."
        )

    def get_incoming_document_pdf(self, uuid: str, doc_type: str = "invoice") -> dict:
        """
        Gelen belge PDF'ini indirir.
        Dönüş: {"ok": bool, "pdf_bytes": bytes|None, "error": str|None}
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} get_incoming_document_pdf() metodunu implement etmedi."
        )

    def get_outgoing_document_pdf(self, uuid: str, doc_type: str = "invoice") -> dict:
        """
        Giden belge PDF'ini indirir.
        Dönüş: {"ok": bool, "pdf_bytes": bytes|None, "error": str|None}
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} get_outgoing_document_pdf() metodunu implement etmedi."
        )
