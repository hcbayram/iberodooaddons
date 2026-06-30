"""
Pazarama REST API istemcisi.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
Cython ile derlenebilir.

Token tabanlı kimlik doğrulaması kullanır.
POST /token ile token alınır; sonraki isteklerde Authorization: Bearer {token} kullanılır.
Token ~24 saat geçerlidir.
"""

import datetime
import requests

from .pazarama_const import PAZARAMA_API_BASE


class PazaramaAPIError(Exception):
    """Pazarama API hatası."""

    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class PazaramaClient:
    """
    Pazarama Marketplace API istemcisi.

    Token tabanlı kimlik doğrulaması:
    - POST /token ile client_id + client_secret kullanılarak token alınır.
    - Sonraki isteklerde Authorization: Bearer {token} başlığı gönderilir.
    - Token süresi dolduğunda otomatik yenilenir (5 dakika önceden).
    """

    def __init__(
        self,
        client_id,
        client_secret,
        access_token=None,
        token_expiry=None,
        on_token_refresh=None,
        timeout=30,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.token_expiry = token_expiry  # datetime.datetime (UTC)
        self.on_token_refresh = on_token_refresh  # callable(token, expiry)
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Başlık ve URL yardımcıları
    # ------------------------------------------------------------------

    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }

    def _url(self, path):
        return f'{PAZARAMA_API_BASE}/{path.lstrip("/")}'

    # ------------------------------------------------------------------
    # HTTP çekirdek
    # ------------------------------------------------------------------

    def _raise_for_status(self, resp):
        if not resp.ok:
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text
            raise PazaramaAPIError(
                f'HTTP {resp.status_code}: {response_body}',
                status_code=resp.status_code,
                response=response_body,
            )

    def _obtain_token(self):
        """POST /token ile yeni token al ve sakla."""
        url = self._url('/token')
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        resp = requests.post(url, data=data, timeout=self.timeout)
        self._raise_for_status(resp)
        payload = resp.json()
        self.access_token = payload.get('access_token') or payload.get('accessToken')
        expires_in = int(payload.get('expires_in') or payload.get('expiresIn') or 86400)
        self.token_expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
        if self.on_token_refresh:
            self.on_token_refresh(self.access_token, self.token_expiry)

    def ensure_token(self):
        """Token yoksa veya süresi dolmuşsa (5 dakika önceden) yenile."""
        margin = datetime.timedelta(minutes=5)
        if (
            not self.access_token
            or not self.token_expiry
            or datetime.datetime.utcnow() >= self.token_expiry - margin
        ):
            self._obtain_token()

    def _request(self, method, url, **kwargs):
        """ensure_token çağırır, istek yapar; 401'de bir kez yeniden dener."""
        self.ensure_token()
        kwargs.setdefault('headers', self._get_headers())
        kwargs.setdefault('timeout', self.timeout)
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 401:
            # Token yenile ve bir kez daha dene
            self._obtain_token()
            kwargs['headers'] = self._get_headers()
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
        GET /api/v1/order/orders?page={page}&pageSize={size}&status=...&startDate=...&endDate=...
        filters: status, startDate, endDate (ISO8601)
        """
        params = {'page': page, 'pageSize': page_size}
        params.update(filters)
        url = self._url('/api/v1/order/orders')
        return self._request('GET', url, params=params)

    def get_order_detail(self, order_code):
        """
        Sipariş detayı.
        GET /api/v1/order/orders/{order_code}
        """
        url = self._url(f'/api/v1/order/orders/{order_code}')
        return self._request('GET', url)

    def send_cargo(self, order_code, cargo_company, tracking_number):
        """
        Kargo bilgisi gönder.
        PUT /api/v1/order/orders/{order_code}/cargo
        """
        url = self._url(f'/api/v1/order/orders/{order_code}/cargo')
        body = {
            'cargoCompany': cargo_company,
            'trackingNumber': tracking_number,
        }
        return self._request('PUT', url, json=body)

    # ------------------------------------------------------------------
    # Stok / Fiyat
    # ------------------------------------------------------------------

    def update_stock(self, items):
        """
        Stok güncelle (max 100 ürün per çağrı).
        POST /api/v1/product/stocks
        items: [{'stockCode': str, 'quantity': int}]
        """
        url = self._url('/api/v1/product/stocks')
        batch = items[:100]
        return self._request('POST', url, json={'items': batch})

    def update_price(self, items):
        """
        Fiyat güncelle.
        POST /api/v1/product/prices
        items: [{'stockCode': str, 'salePrice': float, 'listPrice': float}]
        """
        url = self._url('/api/v1/product/prices')
        batch = items[:100]
        return self._request('POST', url, json={'items': batch})

    # ------------------------------------------------------------------
    # Ürünler
    # ------------------------------------------------------------------

    def get_products(self, page=1, page_size=100):
        """
        Ürün listesi.
        GET /api/v1/product/products?page={page}&pageSize={size}
        """
        params = {'page': page, 'pageSize': page_size}
        url = self._url('/api/v1/product/products')
        return self._request('GET', url, params=params)
