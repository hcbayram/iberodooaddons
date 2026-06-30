import time
from datetime import datetime, timezone

import requests

from .amazon_const import (
    AMAZON_API_BASE,
    AMAZON_LWA_TOKEN_URL,
    AMAZON_MARKETPLACE_ID,
    FEED_TYPE_INVENTORY,
    FEED_TYPE_PRICE,
)


class AmazonAPIError(Exception):
    """Amazon SP-API hatası."""

    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AmazonClient:
    """Amazon Selling Partner API (SP-API) istemcisi.

    Auth: LWA refresh_token → access_token (1 saatlik geçerlilik).
    """

    def __init__(
        self,
        lwa_client_id,
        lwa_client_secret,
        lwa_refresh_token,
        seller_id,
        marketplace_id=AMAZON_MARKETPLACE_ID,
        access_token=None,
        token_expiry=None,
        on_token_refresh=None,
        timeout=30,
    ):
        self.lwa_client_id = lwa_client_id
        self.lwa_client_secret = lwa_client_secret
        self.lwa_refresh_token = lwa_refresh_token
        self.seller_id = seller_id
        self.marketplace_id = marketplace_id
        self._access_token = access_token
        self._token_expiry = token_expiry  # Unix timestamp (float)
        self.on_token_refresh = on_token_refresh
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Token yönetimi
    # ------------------------------------------------------------------

    def _is_token_valid(self):
        if not self._access_token or not self._token_expiry:
            return False
        return time.time() < self._token_expiry - 60  # 60 sn tampon

    def _obtain_token(self):
        resp = requests.post(
            AMAZON_LWA_TOKEN_URL,
            data={
                'grant_type': 'refresh_token',
                'refresh_token': self.lwa_refresh_token,
                'client_id': self.lwa_client_id,
                'client_secret': self.lwa_client_secret,
            },
            timeout=self.timeout,
        )
        if not resp.ok:
            raise AmazonAPIError(
                f'LWA token alınamadı: {resp.status_code} — {resp.text[:300]}',
                status_code=resp.status_code,
            )
        data = resp.json()
        self._access_token = data['access_token']
        expires_in = int(data.get('expires_in', 3600))
        self._token_expiry = time.time() + expires_in

        if self.on_token_refresh:
            self.on_token_refresh(self._access_token, self._token_expiry)

    def _get_token(self):
        if not self._is_token_valid():
            self._obtain_token()
        return self._access_token

    # ------------------------------------------------------------------
    # HTTP yardımcıları
    # ------------------------------------------------------------------

    def _headers(self):
        return {
            'x-amz-access-token': self._get_token(),
            'Content-Type': 'application/json',
        }

    def _url(self, path):
        return f'{AMAZON_API_BASE}/{path.lstrip("/")}'

    def _request(self, method, path, **kwargs):
        url = self._url(path)
        kwargs.setdefault('timeout', self.timeout)
        kwargs['headers'] = self._headers()
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 401:
            # Token süresi dolmuş olabilir — yenile ve tekrar dene
            self._access_token = None
            kwargs['headers'] = self._headers()
            resp = requests.request(method, url, **kwargs)
        if not resp.ok:
            raise AmazonAPIError(
                f'Amazon SP-API hatası: {resp.status_code} — {resp.text[:500]}',
                status_code=resp.status_code,
                response=resp.text,
            )
        return resp

    # ------------------------------------------------------------------
    # Sipariş endpointleri — Orders API v0
    # ------------------------------------------------------------------

    def get_orders(self, created_after=None, order_statuses=None, next_token=None):
        """GET /orders/v0/orders — Sipariş listesi.

        created_after: ISO8601 string (örn. '2024-01-01T00:00:00Z')
        order_statuses: list[str] — boş ise Unshipped + PartiallyShipped
        """
        params = {'MarketplaceIds': self.marketplace_id}
        if created_after:
            params['CreatedAfter'] = created_after
        if order_statuses:
            params['OrderStatuses'] = ','.join(order_statuses)
        if next_token:
            params['NextToken'] = next_token
        resp = self._request('GET', '/orders/v0/orders', params=params)
        return resp.json().get('payload', {})

    def get_order(self, amazon_order_id):
        """GET /orders/v0/orders/{orderId}"""
        resp = self._request('GET', f'/orders/v0/orders/{amazon_order_id}')
        return resp.json().get('payload', {})

    def get_order_items(self, amazon_order_id, next_token=None):
        """GET /orders/v0/orders/{orderId}/orderItems"""
        params = {}
        if next_token:
            params['NextToken'] = next_token
        resp = self._request(
            'GET', f'/orders/v0/orders/{amazon_order_id}/orderItems', params=params)
        return resp.json().get('payload', {})

    def get_order_address(self, amazon_order_id):
        """GET /orders/v0/orders/{orderId}/address"""
        resp = self._request(
            'GET', f'/orders/v0/orders/{amazon_order_id}/address')
        return resp.json().get('payload', {})

    def confirm_shipment(self, amazon_order_id, carrier_code, tracking_number,
                         shipping_date=None, items=None):
        """POST /orders/v0/orders/{orderId}/shipment — Kargo bildirimi."""
        body = {
            'marketplaceId': self.marketplace_id,
            'packageDetail': {
                'packageReferenceId': '1',
                'carrierCode': carrier_code,
                'trackingNumber': tracking_number,
                'shipDate': shipping_date or datetime.now(timezone.utc).strftime(
                    '%Y-%m-%dT%H:%M:%SZ'),
                'orderItems': items or [],
            },
        }
        resp = self._request(
            'POST', f'/orders/v0/orders/{amazon_order_id}/shipment', json=body)
        return resp.json() if resp.text else {}

    # ------------------------------------------------------------------
    # Listings endpointleri — Listings Items API 2021-08-01
    # ------------------------------------------------------------------

    def get_listing(self, sku):
        """GET /listings/2021-08-01/items/{sellerId}/{sku}"""
        path = f'/listings/2021-08-01/items/{self.seller_id}/{sku}'
        params = {
            'marketplaceIds': self.marketplace_id,
            'includedData': 'attributes,fulfillmentAvailability,offers',
        }
        resp = self._request('GET', path, params=params)
        return resp.json()

    # ------------------------------------------------------------------
    # Feeds API — Stok & Fiyat güncelleme
    # ------------------------------------------------------------------

    def _create_feed_document(self, content_type='text/xml; charset=UTF-8'):
        """POST /feeds/2021-06-30/documents — Feed dökümanı oluştur."""
        body = {'contentType': content_type}
        resp = self._request('POST', '/feeds/2021-06-30/documents', json=body)
        return resp.json().get('payload', {})

    def _upload_feed_document(self, upload_url, content, content_type):
        """Feed içeriğini S3 presigned URL'e yükle."""
        resp = requests.put(
            upload_url,
            data=content.encode('utf-8') if isinstance(content, str) else content,
            headers={'Content-Type': content_type},
            timeout=self.timeout,
        )
        if not resp.ok:
            raise AmazonAPIError(
                f'Feed yükleme hatası: {resp.status_code}',
                status_code=resp.status_code,
            )

    def _submit_feed(self, feed_type, feed_document_id):
        """POST /feeds/2021-06-30/feeds — Feed gönder."""
        body = {
            'feedType': feed_type,
            'marketplaceIds': [self.marketplace_id],
            'inputFeedDocumentId': feed_document_id,
        }
        resp = self._request('POST', '/feeds/2021-06-30/feeds', json=body)
        return resp.json().get('payload', {})

    def update_inventory(self, items):
        """Stok güncelleme: items = [{'sku': 'SKU1', 'quantity': 10}, ...]

        XML Feed formatında POST_INVENTORY_AVAILABILITY_DATA kullanır.
        """
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<AmazonEnvelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xsi:noNamespaceSchemaLocation="amzn-envelope.xsd">',
            '  <Header><DocumentVersion>1.01</DocumentVersion>'
            f'<MerchantIdentifier>{self.seller_id}</MerchantIdentifier></Header>',
            '  <MessageType>Inventory</MessageType>',
        ]
        for i, item in enumerate(items, start=1):
            xml_lines += [
                f'  <Message>',
                f'    <MessageID>{i}</MessageID>',
                f'    <OperationType>Update</OperationType>',
                f'    <Inventory>',
                f'      <SKU>{item["sku"]}</SKU>',
                f'      <Quantity>{int(item["quantity"])}</Quantity>',
                f'      <FulfillmentLatency>1</FulfillmentLatency>',
                f'    </Inventory>',
                f'  </Message>',
            ]
        xml_lines.append('</AmazonEnvelope>')
        xml_content = '\n'.join(xml_lines)

        content_type = 'text/xml; charset=UTF-8'
        doc = self._create_feed_document(content_type)
        self._upload_feed_document(doc['url'], xml_content, content_type)
        return self._submit_feed(FEED_TYPE_INVENTORY, doc['feedDocumentId'])

    def update_price(self, items):
        """Fiyat güncelleme: items = [{'sku': 'SKU1', 'price': 99.99, 'currency': 'TRY'}, ...]

        POST_PRODUCT_PRICING_DATA feed kullanır.
        """
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<AmazonEnvelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xsi:noNamespaceSchemaLocation="amzn-envelope.xsd">',
            '  <Header><DocumentVersion>1.01</DocumentVersion>'
            f'<MerchantIdentifier>{self.seller_id}</MerchantIdentifier></Header>',
            '  <MessageType>Price</MessageType>',
        ]
        for i, item in enumerate(items, start=1):
            currency = item.get('currency', 'TRY')
            xml_lines += [
                f'  <Message>',
                f'    <MessageID>{i}</MessageID>',
                f'    <OperationType>Update</OperationType>',
                f'    <Price>',
                f'      <SKU>{item["sku"]}</SKU>',
                f'      <StandardPrice currency="{currency}">'
                f'{item["price"]:.2f}</StandardPrice>',
                f'    </Price>',
                f'  </Message>',
            ]
        xml_lines.append('</AmazonEnvelope>')
        xml_content = '\n'.join(xml_lines)

        content_type = 'text/xml; charset=UTF-8'
        doc = self._create_feed_document(content_type)
        self._upload_feed_document(doc['url'], xml_content, content_type)
        return self._submit_feed(FEED_TYPE_PRICE, doc['feedDocumentId'])

    # ------------------------------------------------------------------
    # Bağlantı testi
    # ------------------------------------------------------------------

    def test_connection(self):
        """Basit bağlantı testi — 1 sipariş çekmeye çalışır."""
        self.get_orders(
            created_after='2024-01-01T00:00:00Z',
            order_statuses=['Unshipped'],
        )
