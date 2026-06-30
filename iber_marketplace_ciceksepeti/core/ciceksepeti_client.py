import requests

from .ciceksepeti_const import CICEKSEPETI_API_BASE


class CiceksepetiAPIError(Exception):
    """Çiçeksepeti API hatası."""

    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class CiceksepetiClient:
    """Çiçeksepeti REST API istemcisi (saf Python — Odoo import içermez)."""

    def __init__(self, api_key, timeout=30):
        self.api_key = api_key
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Dahili yardımcılar
    # ------------------------------------------------------------------

    def _get_headers(self):
        return {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json',
        }

    def _url(self, path):
        return f'{CICEKSEPETI_API_BASE}/{path.lstrip("/")}'

    def _request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('headers', self._get_headers())
        resp = requests.request(method, url, **kwargs)
        self._raise_for_status(resp)
        return resp

    def _raise_for_status(self, resp):
        if not resp.ok:
            raise CiceksepetiAPIError(
                f'Çiçeksepeti API hatası: {resp.status_code} — {resp.text[:500]}',
                status_code=resp.status_code,
                response=resp.text,
            )

    # ------------------------------------------------------------------
    # Sipariş endpointleri
    # ------------------------------------------------------------------

    def get_orders(self, page=0, page_size=100, **filters):
        """GET /api/v1/orders — Sipariş listesi."""
        params = {'page': page, 'pageSize': page_size}
        params.update(filters)
        resp = self._request('GET', self._url('/api/v1/orders'), params=params)
        return resp.json()

    def get_order_detail(self, order_code):
        """GET /api/v1/orders/{order_code} — Sipariş detayı."""
        resp = self._request('GET', self._url(f'/api/v1/orders/{order_code}'))
        return resp.json()

    def ship_order_item(self, order_code, order_item_code, cargo_company, tracking_number):
        """POST /api/v1/orders/{orderCode}/items/{orderItemCode}/status — Kargo bildirimi."""
        url = self._url(f'/api/v1/orders/{order_code}/items/{order_item_code}/status')
        body = {
            'status': 'Shipped',
            'trackingNumber': tracking_number,
            'cargoCompany': cargo_company,
        }
        resp = self._request('POST', url, json=body)
        return resp.json() if resp.text else {}

    # ------------------------------------------------------------------
    # Stok / Fiyat endpointleri
    # ------------------------------------------------------------------

    def update_stock(self, items):
        """POST /api/v1/products/stock — Stok güncelleme.

        items: [{'stockCode': 'SKU', 'stock': 10}, ...]  (max 100 per call)
        """
        resp = self._request(
            'POST', self._url('/api/v1/products/stock'), json={'items': items})
        return resp.json() if resp.text else {}

    def update_price(self, items):
        """POST /api/v1/products/price — Fiyat güncelleme.

        items: [{'stockCode': 'SKU', 'salesPrice': 99.99, 'listPrice': 119.99}, ...]
        """
        resp = self._request(
            'POST', self._url('/api/v1/products/price'), json={'items': items})
        return resp.json() if resp.text else {}

    # ------------------------------------------------------------------
    # Ürün endpointleri
    # ------------------------------------------------------------------

    def get_products(self, page=0, page_size=100):
        """GET /api/v1/products — Ürün listesi."""
        params = {'page': page, 'pageSize': page_size}
        resp = self._request('GET', self._url('/api/v1/products'), params=params)
        return resp.json()
