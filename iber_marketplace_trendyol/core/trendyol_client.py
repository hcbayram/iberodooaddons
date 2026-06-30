"""
Trendyol REST API istemcisi.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
Cython ile derlenebilir.
"""

import base64
import json
import requests

from .trendyol_const import TRENDYOL_API_BASE


class TrendyolAPIError(Exception):
    """Trendyol API hatası."""

    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class TrendyolClient:
    """
    Trendyol Supplier Integration API istemcisi.

    Basic Auth kullanır: api_key:api_secret base64 kodlanır.
    Her istek için Authorization: Basic <token> başlığı gönderilir.
    """

    def __init__(self, merchant_id, api_key, api_secret, timeout=30):
        self.merchant_id = str(merchant_id)
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Başlık ve URL yardımcıları
    # ------------------------------------------------------------------

    def _get_headers(self):
        credentials = f'{self.api_key}:{self.api_secret}'
        encoded = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return {
            'Authorization': f'Basic {encoded}',
            'User-Agent': f'{self.merchant_id} - SelfIntegration',
            'Content-Type': 'application/json',
        }

    def _supplier_url(self, path):
        return f'{TRENDYOL_API_BASE}/suppliers/{self.merchant_id}/{path}'

    # ------------------------------------------------------------------
    # HTTP çekirdek
    # ------------------------------------------------------------------

    def _raise_for_status(self, resp):
        if not resp.ok:
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text
            raise TrendyolAPIError(
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

    def get_orders(self, page=0, size=50, **filters):
        """
        Sipariş listesi.
        GET /suppliers/{id}/orders?page=0&size=50[&status=...][&startDate=...][&endDate=...]
        """
        params = {'page': page, 'size': size}
        params.update(filters)
        url = self._supplier_url('orders')
        return self._request('GET', url, params=params)

    # ------------------------------------------------------------------
    # Kargo / Sevkiyat
    # ------------------------------------------------------------------

    def update_shipment(self, lines):
        """
        Kargo bilgisi güncelle.
        PUT /suppliers/{id}/shipments
        lines: [{'orderLineId': int, 'shipmentPackageId': int (optional),
                 'cargoProviderName': str, 'trackingNumber': str}]
        """
        url = self._supplier_url('shipments')
        return self._request('PUT', url, json={'lines': lines})

    # ------------------------------------------------------------------
    # Stok / Fiyat
    # ------------------------------------------------------------------

    def update_inventory(self, items):
        """
        Stok ve fiyat güncelle (max 100 ürün).
        POST /suppliers/{id}/products/price-and-inventory
        items: [{'barcode': str, 'quantity': int, 'salePrice': float, 'listPrice': float}]
        """
        url = self._supplier_url('products/price-and-inventory')
        # Trendyol max 100 item per request
        batch = items[:100]
        return self._request('POST', url, json={'items': batch})

    # ------------------------------------------------------------------
    # Ürünler
    # ------------------------------------------------------------------

    def get_products(self, page=0, size=50, **filters):
        """
        Ürün listesi.
        GET /suppliers/{id}/products?page=0&size=50
        """
        params = {'page': page, 'size': size}
        params.update(filters)
        url = self._supplier_url('products')
        return self._request('GET', url, params=params)
