"""
N11 SOAP API istemcisi.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
Cython ile derlenebilir.
"""

import re
import xml.etree.ElementTree as ET
import requests

from .n11_const import (
    N11_ORDER_SERVICE_URL,
    N11_STOCK_SERVICE_URL,
    N11_SCHEMAS_NS,
    N11_SOAP_NS,
)


class N11Error(Exception):
    """N11 SOAP API hatası."""

    def __init__(self, message, fault_code=None, result_code=None):
        super().__init__(message)
        self.fault_code = fault_code
        self.result_code = result_code


def _strip_ns(tag):
    """XML etiketinden namespace'i kaldırır."""
    return re.sub(r'\{[^}]+\}', '', tag)


def _elem_to_dict(elem):
    """XML element'ini özyinelemeli olarak dict'e çevirir. Tekrarlı çocuklar liste olur."""
    children = list(elem)
    if not children:
        return (elem.text or '').strip()
    result = {}
    for child in children:
        key = _strip_ns(child.tag)
        val = _elem_to_dict(child)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(val)
        else:
            result[key] = val
    return result


def _ensure_list(val):
    """Değeri liste olarak döndürür; None → [], tekil değer → [değer]."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


class N11Client:
    """
    N11 SOAP API istemcisi.
    xml.etree.ElementTree + requests kullanır (zeep gerektirmez).

    app_key: N11 API anahtarı
    app_secret: N11 API gizli anahtarı
    timeout: HTTP istek zaman aşımı (saniye)
    """

    def __init__(self, app_key, app_secret, timeout=30):
        self.app_key = app_key
        self.app_secret = app_secret
        self.timeout = timeout

    # ------------------------------------------------------------------
    # SOAP altyapı yardımcıları
    # ------------------------------------------------------------------

    def _auth_xml(self):
        """Her isteğe eklenen kimlik doğrulama bloğunu döndürür."""
        return (
            '<auth>'
            f'<appKey>{self.app_key}</appKey>'
            f'<appSecret>{self.app_secret}</appSecret>'
            '</auth>'
        )

    def _wrap_envelope(self, body_xml):
        """SOAP zarfını oluşturur."""
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<soapenv:Envelope xmlns:soapenv="{N11_SOAP_NS}" xmlns:sch="{N11_SCHEMAS_NS}">'
            f'<soapenv:Body>{body_xml}</soapenv:Body>'
            '</soapenv:Envelope>'
        )

    def _call(self, service_url, action, body_xml):
        """
        Belirtilen service_url'e SOAP isteği gönderir.
        SOAPAction başlığı: "action"
        Yanıtı namespace'siz dict olarak döndürür.
        """
        envelope = self._wrap_envelope(body_xml)
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': f'"{action}"',
        }
        try:
            resp = requests.post(
                service_url,
                data=envelope.encode('utf-8'),
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise N11Error(f'HTTP bağlantı hatası: {exc}')

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            raise N11Error(f'SOAP yanıt ayrıştırma hatası: {exc}')

        # SOAP Fault kontrolü
        fault = root.find('.//{%s}Fault' % N11_SOAP_NS)
        if fault is not None:
            code_el = fault.find('faultcode')
            str_el = fault.find('faultstring')
            code = code_el.text if code_el is not None else ''
            msg = str_el.text if str_el is not None else resp.text
            raise N11Error(f'SOAP Fault [{code}]: {msg}', fault_code=code)

        if not resp.ok:
            raise N11Error(f'HTTP {resp.status_code}: {resp.text[:500]}')

        # Body'nin ilk çocuğunu dict olarak döndür
        body = root.find('.//{%s}Body' % N11_SOAP_NS)
        if body is None:
            return {}
        children = list(body)
        if not children:
            return {}
        return _elem_to_dict(children[0])

    def _check_result(self, data):
        """
        N11 yanıt result.status alanını kontrol eder.
        'success' değilse N11Error fırlatır.
        """
        result = data.get('result') or {}
        if isinstance(result, str):
            # Bazı yanıtlarda result düz string olabilir
            return
        status = result.get('status') or ''
        if status.lower() != 'success':
            code = result.get('errorCode') or result.get('resultCode') or ''
            msg = result.get('errorMessage') or result.get('errorDesc') or str(result)
            raise N11Error(
                f'N11 API hatası [{code}]: {msg}',
                result_code=code,
            )

    # ------------------------------------------------------------------
    # Sipariş servisi
    # ------------------------------------------------------------------

    def get_orders(self, page=0, page_size=100, status=None,
                   start_date=None, end_date=None):
        """
        GetOrderListRequest — sayfalı sipariş listesi.

        status: N11 durum kodu (New, Approved, vb.) — None ise gönderilmez
        start_date / end_date: DD/MM/YYYY formatında tarih string'leri
        Döndürür: sipariş dict listesi (boş olabilir)
        """
        search_data_parts = []
        if status:
            search_data_parts.append(f'<status>{status}</status>')
        if start_date or end_date:
            period_parts = []
            if start_date:
                period_parts.append(f'<startDate>{start_date}</startDate>')
            if end_date:
                period_parts.append(f'<endDate>{end_date}</endDate>')
            search_data_parts.append(
                '<period>' + ''.join(period_parts) + '</period>'
            )
        search_data_xml = (
            '<searchData>' + ''.join(search_data_parts) + '</searchData>'
            if search_data_parts else '<searchData/>'
        )

        body = (
            '<sch:GetOrderListRequest>'
            + self._auth_xml()
            + search_data_xml
            + f'<pagingData>'
            + f'<currentPage>{int(page)}</currentPage>'
            + f'<pageSize>{int(page_size)}</pageSize>'
            + '</pagingData>'
            + '</sch:GetOrderListRequest>'
        )
        data = self._call(N11_ORDER_SERVICE_URL, 'GetOrderList', body)
        self._check_result(data)
        order_list = data.get('orderList') or {}
        if isinstance(order_list, str):
            return []
        orders = order_list.get('order') or []
        return _ensure_list(orders)

    def get_order_detail(self, order_id):
        """
        GetOrderDetailRequest — tek sipariş detayı.
        Döndürür: sipariş dict.
        """
        body = (
            '<sch:GetOrderDetailRequest>'
            + self._auth_xml()
            + f'<orderRequest><id>{order_id}</id></orderRequest>'
            + '</sch:GetOrderDetailRequest>'
        )
        data = self._call(N11_ORDER_SERVICE_URL, 'GetOrderDetail', body)
        self._check_result(data)
        return data.get('order') or {}

    def set_shipping(self, order_id, cargo_company, tracking_number):
        """
        SetOrderStatusToShippingRequest — siparişi kargoya verildi olarak işaretle.

        order_id: N11 sipariş ID
        cargo_company: kargo şirketi kodu (ör. ARAS_KARGO)
        tracking_number: kargo takip numarası
        """
        body = (
            '<sch:SetOrderStatusToShippingRequest>'
            + self._auth_xml()
            + '<orderRequest>'
            + f'<orderId>{order_id}</orderId>'
            + f'<shipmentCompany>{cargo_company}</shipmentCompany>'
            + f'<trackingNumber>{tracking_number}</trackingNumber>'
            + '</orderRequest>'
            + '</sch:SetOrderStatusToShippingRequest>'
        )
        data = self._call(N11_ORDER_SERVICE_URL, 'SetOrderStatusToShipping', body)
        self._check_result(data)
        return data

    def update_stock_items(self, items):
        """
        UpdateStockByStockSellerCodeRequest — stok güncelleme.

        items: [{'seller_stock_code': str, 'quantity': int}] — max 100 kayıt
        """
        stock_items_xml = ''
        for item in items[:100]:
            stock_items_xml += (
                '<stockItem>'
                f'<sellerStockCode>{item["seller_stock_code"]}</sellerStockCode>'
                f'<quantity>{int(item["quantity"])}</quantity>'
                '</stockItem>'
            )

        body = (
            '<sch:UpdateStockByStockSellerCodeRequest>'
            + self._auth_xml()
            + '<stockItems>'
            + stock_items_xml
            + '</stockItems>'
            + '</sch:UpdateStockByStockSellerCodeRequest>'
        )
        data = self._call(N11_STOCK_SERVICE_URL, 'UpdateStockByStockSellerCode', body)
        self._check_result(data)
        return data
