"""
Hepsiburada REST API istemcisi.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
Cython ile derlenebilir.

İki ayrı base URL kullanır:
  - Listing API: listing-external.hepsiburada.com — ürün/stok/fiyat
  - MPOP API:    mpop.hepsiburada.com             — sipariş yönetimi
"""

import base64
import requests

from .hepsiburada_const import MPOP_API_BASE, LISTING_API_BASE


class HepsiburadaAPIError(Exception):
    """Hepsiburada API hatası."""

    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class HepsiburadaClient:
    """
    Hepsiburada Marketplace API istemcisi.

    Basic Auth kullanır: username:password base64 kodlanır.
    Her istek için Authorization: Basic <token> başlığı gönderilir.
    """

    def __init__(self, username, password, merchant_id=None, timeout=30):
        self.username = username
        self.password = password
        self.merchant_id = merchant_id
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Başlık ve URL yardımcıları
    # ------------------------------------------------------------------

    def _get_headers(self):
        credentials = f'{self.username}:{self.password}'
        encoded = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return {
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/json',
        }

    def _mpop_url(self, path):
        return f'{MPOP_API_BASE}{path}'

    def _listing_url(self, path):
        return f'{LISTING_API_BASE}{path}'

    # ------------------------------------------------------------------
    # HTTP çekirdek
    # ------------------------------------------------------------------

    def _raise_for_status(self, resp):
        if not resp.ok:
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text
            raise HepsiburadaAPIError(
                f'HTTP {resp.status_code}: {response_body}',
                status_code=resp.status_code,
                response=response_body,
            )

    def _request(self, method, url, **kwargs):
        kwargs.setdefault('headers', self._get_headers())
        kwargs.setdefault('timeout', self.timeout)
        resp = requests.request(method, url, **kwargs)
        # 202 Accepted — async işlem, başarı sayılır
        if resp.status_code == 202:
            if resp.content:
                try:
                    return resp.json()
                except Exception:
                    return {}
            return {}
        self._raise_for_status(resp)
        if resp.content:
            try:
                return resp.json()
            except Exception:
                return {}
        return {}

    # ------------------------------------------------------------------
    # Siparişler (MPOP API)
    # ------------------------------------------------------------------

    def get_orders(self, offset=0, limit=100, **filters):
        """
        Sipariş listesi.
        GET /api/orders?offset=0&limit=100[&status=...][&beginDate=...][&endDate=...]
        """
        params = {'offset': offset, 'limit': limit}
        params.update(filters)
        url = self._mpop_url('/api/orders')
        return self._request('GET', url, params=params)

    def get_order_detail(self, order_id):
        """
        Sipariş detayı.
        GET /api/orders/{order_id}
        """
        url = self._mpop_url(f'/api/orders/{order_id}')
        return self._request('GET', url)

    def send_shipment(self, order_id, line_item_id, cargo_company, tracking_number):
        """
        Kargo bilgisi gönder.
        POST /api/orders/{order_id}/lines/{line_item_id}/shipmentInfo
        """
        url = self._mpop_url(
            f'/api/orders/{order_id}/lines/{line_item_id}/shipmentInfo'
        )
        body = {
            'cargoCompany': cargo_company,
            'trackingNumber': tracking_number,
        }
        return self._request('POST', url, json=body)

    # ------------------------------------------------------------------
    # Stok / Fiyat (Listing API)
    # ------------------------------------------------------------------

    def update_inventory(self, items):
        """
        Stok güncelle (max 100 ürün).
        POST /api/stocks/update
        items: [{'hepsiburadaSku': str, 'availableStock': int}]
        """
        url = self._listing_url('/api/stocks/update')
        batch = items[:100]
        return self._request('POST', url, json={'items': batch})

    def update_prices(self, items):
        """
        Fiyat güncelle.
        POST /api/price/update
        items: [{'hepsiburadaSku': str, 'listPrice': float, 'salePrice': float}]
        """
        url = self._listing_url('/api/price/update')
        batch = items[:100]
        return self._request('POST', url, json={'items': batch})

    # ------------------------------------------------------------------
    # Ürünler (Listing API)
    # ------------------------------------------------------------------

    def get_products(self, offset=0, limit=100, **filters):
        """
        Ürün listesi.
        GET /api/merchants/{merchant_id}/products?offset=0&limit=100
        """
        if not self.merchant_id:
            raise HepsiburadaAPIError(
                'merchant_id gerekli — get_products çağrısı için.')
        params = {'offset': offset, 'limit': limit}
        params.update(filters)
        url = self._listing_url(f'/api/merchants/{self.merchant_id}/products')
        return self._request('GET', url, params=params)
