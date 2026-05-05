import requests
from datetime import datetime, timedelta

ENTEGRA_BASE_URL = 'https://apiv2.entegrabilisim.com'

# Access token yenileme için 10 dk erken tetikle
_ACCESS_REFRESH_MARGIN = timedelta(minutes=10)
_REFRESH_EXPIRY_MARGIN = timedelta(hours=1)


class EntegraAPIError(Exception):
    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class EntegraClient:
    """
    Entegra REST API istemcisi.
    Odoo'ya bağımlılık yoktur; core/ katmanında tutulur.

    Sayfalama notu: Entegra liste endpoint'leri page parametresini
    query string değil, path içinde alır → /order/page=1/

    on_token_refresh(access, refresh, access_expiry, refresh_expiry) callback'i
    token yenilendiğinde çağrılır — Odoo model bu callback'te veritabanını günceller.
    """

    def __init__(self, email, password,
                 access_token=None, refresh_token=None,
                 access_expiry=None, refresh_expiry=None,
                 on_token_refresh=None):
        self.email = email
        self.password = password
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._access_expiry = access_expiry    # datetime (UTC, naive)
        self._refresh_expiry = refresh_expiry  # datetime (UTC, naive)
        self.on_token_refresh = on_token_refresh

    # ------------------------------------------------------------------
    # Token yönetimi
    # ------------------------------------------------------------------

    def _is_access_valid(self):
        if not self._access_token or not self._access_expiry:
            return False
        return datetime.utcnow() < self._access_expiry - _ACCESS_REFRESH_MARGIN

    def _is_refresh_valid(self):
        if not self._refresh_token or not self._refresh_expiry:
            return False
        return datetime.utcnow() < self._refresh_expiry - _REFRESH_EXPIRY_MARGIN

    def _obtain_token(self):
        resp = requests.post(
            f'{ENTEGRA_BASE_URL}/api/user/token/obtain/',
            json={'email': self.email, 'password': self.password},
            headers={'Content-Type': 'application/json'},
            timeout=30,
        )
        self._raise_for_status(resp)
        data = resp.json()
        now = datetime.utcnow()
        self._access_token = data['access']
        self._refresh_token = data['refresh']
        self._access_expiry = now + timedelta(days=7)
        self._refresh_expiry = now + timedelta(days=30)
        self._notify_token_refresh()

    def _refresh_access_token(self):
        resp = requests.post(
            f'{ENTEGRA_BASE_URL}/api/user/token/refresh/',
            json={'refresh': self._refresh_token},
            headers={'Content-Type': 'application/json'},
            timeout=30,
        )
        self._raise_for_status(resp)
        data = resp.json()
        self._access_token = data['access']
        self._access_expiry = datetime.utcnow() + timedelta(days=7)
        self._notify_token_refresh()

    def _notify_token_refresh(self):
        if self.on_token_refresh:
            self.on_token_refresh(
                self._access_token,
                self._refresh_token,
                self._access_expiry,
                self._refresh_expiry,
            )

    def ensure_token(self):
        if self._is_access_valid():
            return
        if self._is_refresh_valid():
            try:
                self._refresh_access_token()
                return
            except Exception:
                pass
        self._obtain_token()

    # ------------------------------------------------------------------
    # HTTP yardımcıları
    # ------------------------------------------------------------------

    def _headers(self):
        return {
            'Authorization': f'JWT {self._access_token}',
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _raise_for_status(resp):
        if not resp.ok:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise EntegraAPIError(
                f'HTTP {resp.status_code}: {detail}',
                status_code=resp.status_code,
                response=detail,
            )

    def request(self, method, path, **kwargs):
        self.ensure_token()
        resp = requests.request(
            method,
            f'{ENTEGRA_BASE_URL}{path}',
            headers=self._headers(),
            timeout=30,
            **kwargs,
        )
        self._raise_for_status(resp)
        try:
            return resp.json()
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Ürünler — Products
    # Sayfalama: /product/page=N/   (page path içinde)
    # ------------------------------------------------------------------

    def get_products(self, page=1, params=None):
        """Ürün listesi — GET /product/page=N/"""
        return self.request('GET', f'/product/page={page}/', params=params)

    def get_products_v2(self, payload):
        """Detaylı ürün listesi — GET /product/list/v2/ (body ile)"""
        return self.request('GET', '/product/list/v2/', json=payload)

    def create_product(self, payload):
        """Ürün oluştur — POST /product/"""
        return self.request('POST', '/product/', json=payload)

    def create_product_v2(self, payload):
        """Ürün oluştur v2 — POST /product/v2/"""
        return self.request('POST', '/product/v2/', json=payload)

    def update_product(self, payload):
        """Genel ürün güncelle (fiyat/stok/alan) — PUT /product/
        Payload örneği: {'list': [{'productCode': '...', 'quantity': 10, 'price1': 99.9}]}
        """
        return self.request('PUT', '/product/', json=payload)

    def update_product_full(self, payload):
        """Kapsamlı ürün güncelle (tüm alanlar) — PUT /product/update/"""
        return self.request('PUT', '/product/update/', json=payload)

    def update_product_prices(self, payload):
        """Pazaryeri fiyatlarını güncelle — PUT /product/prices/
        Payload örneği: {'list': [{'productCode': '...', 'prices': [
            {'store_id': 0, 'priceCode': 'trendyol_salePrice', 'priceValue': 99.9}
        ]}]}
        """
        return self.request('PUT', '/product/prices/', json=payload)

    def update_product_quantity(self, payload):
        """Stok güncelle — PUT /product/quantity/
        Payload örneği: {'list': [{'productCode': '...', 'store_id': 0, 'quantity': 10}]}
        """
        return self.request('PUT', '/product/quantity/', json=payload)

    def update_product_variations(self, payload):
        """Varyant güncelle — PUT /product/variations/"""
        return self.request('PUT', '/product/variations/', json=payload)

    def update_product_variation_price(self, payload):
        """Varyant fiyat güncelle — PUT /product/variation/price/"""
        return self.request('PUT', '/product/variation/price/', json=payload)

    def update_product_variation_quantity(self, payload):
        """Varyant stok güncelle — PUT /product/variation/quantity/"""
        return self.request('PUT', '/product/variation/quantity/', json=payload)

    def add_product_pictures(self, payload):
        """Ürün resmi ekle — POST /product/pictures/"""
        return self.request('POST', '/product/pictures/', json=payload)

    def add_product_variations(self, payload):
        """Varyant ekle — POST /product/variations/"""
        return self.request('POST', '/product/variations/', json=payload)

    # ------------------------------------------------------------------
    # Kategoriler — Categories
    # Sayfalama: /category/page=N/
    # ------------------------------------------------------------------

    def get_categories(self, page=1, params=None):
        """Kategori listesi — GET /category/page=N/"""
        return self.request('GET', f'/category/page={page}/', params=params)

    # ------------------------------------------------------------------
    # Siparişler — Orders
    # Sayfalama: /order/page=N/
    # ------------------------------------------------------------------

    def get_orders(self, page=1, params=None):
        """Sipariş listesi — GET /order/page=N/
        Desteklenen query params: limit, api_sync, supplier, status
        """
        return self.request('GET', f'/order/page={page}/', params=params)

    def create_order(self, payload):
        """Sipariş oluştur — POST /order/"""
        return self.request('POST', '/order/', json=payload)

    def update_order(self, payload):
        """Sipariş güncelle (durum/kargo) — PUT /order/
        Payload örneği: {'list': [{'id': 9, 'status': 2}]}
        """
        return self.request('PUT', '/order/', json=payload)

    def update_order_erp(self, payload):
        """ERP sync güncelle — PUT /order/update/
        Payload örneği: {'list': [{'id': 9, 'api_sync': 1, 'erp_order_number': '...'}]}
        """
        return self.request('PUT', '/order/update/', json=payload)

    def send_shipment(self, payload):
        """Kargo bildir — POST /order/sendShipment
        Payload örneği: {'list': [{'orders': [{'order_number': 123, 'ship_name': 'aras'}]}]}
        """
        return self.request('POST', '/order/sendShipment', json=payload)

    def cancel_cargo(self, payload):
        """Kargo iptal — POST /order/cargoCancel"""
        return self.request('POST', '/order/cargoCancel', json=payload)

    # ------------------------------------------------------------------
    # Mağazalar — Stores
    # Sayfalama yok
    # ------------------------------------------------------------------

    def get_stores(self, params=None):
        """Mağaza listesi — GET /store/getStores"""
        return self.request('GET', '/store/getStores', params=params)

    def get_marketplace_qty_settings(self, params=None):
        """Pazaryeri stok ayarları — GET /store/getMarketplaceQuantitySettings"""
        return self.request('GET', '/store/getMarketplaceQuantitySettings', params=params)

    # ------------------------------------------------------------------
    # Markalar — Brands
    # Sayfalama: /product/brand/page=N/
    # ------------------------------------------------------------------

    def get_brands(self, page=1, params=None):
        """Marka listesi — GET /product/brand/page=N/"""
        return self.request('GET', f'/product/brand/page={page}/', params=params)

    # ------------------------------------------------------------------
    # Fiyatlar — Prices
    # Sayfalama yok
    # ------------------------------------------------------------------

    def get_prices(self, params=None):
        """Fiyat listesi — GET /price/getPrices"""
        return self.request('GET', '/price/getPrices', params=params)

    def get_marketplace_price_settings(self, params=None):
        """Pazaryeri fiyat ayarları — GET /price/getMarketplacePriceSettings"""
        return self.request('GET', '/price/getMarketplacePriceSettings', params=params)

    # ------------------------------------------------------------------
    # Müşteriler — Customers
    # Sayfalama: /customer/page=N/
    # ------------------------------------------------------------------

    def get_customers(self, page=1, params=None):
        """Müşteri listesi — GET /customer/page=N/"""
        return self.request('GET', f'/customer/page={page}/', params=params)
