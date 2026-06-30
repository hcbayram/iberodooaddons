"""
PttAVM REST API istemcisi.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
Cython ile derlenebilir.

Bearer token (api_key) kimlik doğrulaması kullanır.
Base URL: https://www.pttavm.com/api
"""

import requests

from .pttavm_const import PTTAVM_API_BASE


class PttavmAPIError(Exception):
    """PttAVM API hatası."""

    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class PttavmClient:
    """
    PttAVM Marketplace API istemcisi.

    Bearer token kimlik doğrulaması kullanır.
    Her istek için Authorization: Bearer {api_key} başlığı gönderilir.
    """

    def __init__(self, api_key, timeout=30):
        self.api_key = api_key
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Başlık ve URL yardımcıları
    # ------------------------------------------------------------------

    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def _url(self, path):
        return f'{PTTAVM_API_BASE}/{path.lstrip("/")}'

    # ------------------------------------------------------------------
    # HTTP çekirdek
    # ------------------------------------------------------------------

    def _raise_for_status(self, resp):
        if not resp.ok:
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text
            raise PttavmAPIError(
                f'HTTP {resp.status_code}: {response_body}',
                status_code=resp.status_code,
                response=response_body,
            )

    def _request(self, method, url, **kwargs):
        kwargs.setdefault('headers', self._get_headers())
        kwargs.setdefault('timeout', self.timeout)
        resp = requests.request(method, url, **kwargs)
        self._raise_for_status(resp)
        if resp.content:
            try:
                return resp.json()
            except Exception:
                return {}
        return {}

    # ------------------------------------------------------------------
    # Siparişler
    # ------------------------------------------------------------------

    def get_orders(self, page=1, page_size=100, **filters):
        """
        Sipariş listesi.
        GET /orders?page={page}&pageSize={size}&status={status}&startDate={date}&endDate={date}
        filters: status, startDate, endDate (ISO8601)
        """
        params = {'page': page, 'pageSize': page_size}
        params.update(filters)
        url = self._url('/orders')
        return self._request('GET', url, params=params)

    def get_order_detail(self, order_id):
        """
        Sipariş detayı.
        GET /orders/{order_id}
        """
        url = self._url(f'/orders/{order_id}')
        return self._request('GET', url)

    def send_cargo(self, order_id, cargo_company, tracking_no, tracking_url=''):
        """
        Kargo bilgisi gönder.
        PUT /orders/{order_id}/cargo
        """
        url = self._url(f'/orders/{order_id}/cargo')
        body = {
            'cargoCompany': cargo_company,
            'cargoTrackingNo': tracking_no,
            'cargoTrackingUrl': tracking_url or '',
        }
        return self._request('PUT', url, json=body)

    # ------------------------------------------------------------------
    # Stok / Fiyat
    # ------------------------------------------------------------------

    def update_stock(self, products):
        """
        Stok güncelle (max 100 ürün).
        POST /products/update-stock
        products: [{'barcode': str, 'stockQuantity': int}]
        """
        url = self._url('/products/update-stock')
        batch = products[:100]
        return self._request('POST', url, json={'products': batch})

    def update_price(self, products):
        """
        Fiyat güncelle.
        POST /products/update-price
        products: [{'barcode': str, 'salePrice': float, 'listPrice': float}]
        """
        url = self._url('/products/update-price')
        batch = products[:100]
        return self._request('POST', url, json={'products': batch})

    # ------------------------------------------------------------------
    # Ürünler
    # ------------------------------------------------------------------

    def get_products(self, page=1, page_size=100, **filters):
        """
        Ürün listesi.
        GET /products?page={page}&pageSize={size}
        """
        params = {'page': page, 'pageSize': page_size}
        params.update(filters)
        url = self._url('/products')
        return self._request('GET', url, params=params)
