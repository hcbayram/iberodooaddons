"""
Pavo 507 POS REST API istemcisi.
Odoo bağımlılığı yoktur; core/ katmanında tutulur.

Tüm istekler POST olarak gönderilir.
HTTPS: port 4567  |  HTTP: port 4568
"""

import requests
import urllib3
from datetime import datetime, timezone

# Self-signed sertifika uyarısını bastır (yerel ağ POS cihazı)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class PavoAPIError(Exception):
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code


class PavoClient:
    """
    Pavo 507 REST API istemcisi.

    on_sequence_update(new_seq) callback'i her başarılı istekten sonra
    çağrılır — Odoo model bu callback'te transaction_sequence'ı günceller.
    """

    def __init__(self, ip, use_ssl, serial_number, fingerprint,
                 transaction_sequence=0,
                 referer_app='IberOdoo', referer_app_version='19.0.1.0.0',
                 timeout=60, on_sequence_update=None):
        self.ip = ip
        self.use_ssl = use_ssl
        self.serial_number = serial_number
        self.fingerprint = fingerprint
        self.transaction_sequence = transaction_sequence
        self.referer_app = referer_app
        self.referer_app_version = referer_app_version
        self.timeout = timeout
        self.on_sequence_update = on_sequence_update

    # ------------------------------------------------------------------
    # Bağlantı yardımcıları
    # ------------------------------------------------------------------

    @property
    def port(self):
        return 4567 if self.use_ssl else 4568

    def _base_url(self):
        proto = 'https' if self.use_ssl else 'http'
        return f'{proto}://{self.ip}:{self.port}'

    def _next_sequence(self):
        self.transaction_sequence += 1
        if self.on_sequence_update:
            self.on_sequence_update(self.transaction_sequence)
        return self.transaction_sequence

    def _transaction_handle(self):
        return {
            'SerialNumber': self.serial_number,
            'Fingerprint': self.fingerprint,
            'TransactionSequence': self._next_sequence(),
            'TransactionDate': datetime.now(timezone.utc).isoformat(),
        }

    def _post(self, endpoint, payload):
        url = f'{self._base_url()}/{endpoint}'
        resp = requests.post(
            url, json=payload,
            timeout=self.timeout,
            verify=False,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _check(data):
        if data.get('HasError'):
            msg = data.get('Message') or data.get('ErrorMessage') or 'Pavo hatası'
            raise PavoAPIError(msg, error_code=data.get('ErrorCode'))
        return data

    # ------------------------------------------------------------------
    # 1. Giriş / Oturum
    # ------------------------------------------------------------------

    def pair(self):
        """Cihaz eşleştirme — TransactionHandle sekansı burada sıfırdan başlar."""
        payload = {
            'TransactionHandle': {
                'SerialNumber': self.serial_number,
                'TransactionDate': datetime.now(timezone.utc).isoformat(),
                'TransactionSequence': 1,
                'Fingerprint': self.fingerprint,
            }
        }
        return self._check(self._post('Pairing', payload))

    def ping(self):
        """Bağlantı kontrolü — TransactionHandle gönderilmez."""
        return self._post('Ping', {})

    # ------------------------------------------------------------------
    # 2. Satış Başlatma
    # ------------------------------------------------------------------

    def start_sale_with_items(self, items, gross_price, total_price,
                              order_no=None, main_document_type=1,
                              currency_code=None, customer_party=None,
                              extra=None):
        """
        Sepet ile satış başlat (StartSaleWithItems).

        items: AddedSaleItems listesi
          Her eleman: {Name, Barcode, ItemQuantity, UnitPriceAmount,
                       GrossPriceAmount, TotalPriceAmount, TaxGroupCode, UnitCode, IsGeneric}
        """
        sale = {
            'RefererApp': self.referer_app,
            'RefererAppVersion': self.referer_app_version,
            'MainDocumentType': main_document_type,
            'GrossPrice': gross_price,
            'TotalPrice': total_price,
            'AddedSaleItems': items,
        }
        if order_no:
            sale['OrderNo'] = order_no
        if currency_code and currency_code != 'TRY':
            sale['CurrencyCode'] = currency_code
        if customer_party:
            sale['CustomerParty'] = customer_party
        if extra:
            sale.update(extra)

        payload = {'TransactionHandle': self._transaction_handle(), 'Sale': sale}
        return self._check(self._post('StartSaleWithItems', payload))

    def advance_sale(self, total_amount, sale_reason, order_no=None,
                     invoice_data=None, currency_code=None,
                     customer_party=None, extra=None):
        """Avans ödeme (AdvanceSale)."""
        sale = {
            'RefererApp': self.referer_app,
            'RefererAppVersion': self.referer_app_version,
            'TotalAmount': total_amount,
            'SaleReason': sale_reason,
        }
        if order_no:
            sale['OrderNo'] = order_no
        if invoice_data:
            sale['InvoiceData'] = invoice_data
        if currency_code and currency_code != 'TRY':
            sale['CurrencyCode'] = currency_code
        if customer_party:
            sale['CustomerParty'] = customer_party
        if extra:
            sale.update(extra)

        payload = {'TransactionHandle': self._transaction_handle(), 'Sale': sale}
        return self._check(self._post('AdvanceSale', payload))

    def current_sale(self, total_amount, sale_reason, invoice_data,
                     order_no=None, currency_code=None,
                     customer_party=None, extra=None):
        """
        Cari ödeme (CurrentSale).

        invoice_data: [{InvoiceNo, InvoiceDate}, ...] — zorunlu, boş olamaz
        """
        sale = {
            'RefererApp': self.referer_app,
            'RefererAppVersion': self.referer_app_version,
            'TotalAmount': total_amount,
            'SaleReason': sale_reason,
            'InvoiceData': invoice_data,
        }
        if order_no:
            sale['OrderNo'] = order_no
        if currency_code and currency_code != 'TRY':
            sale['CurrencyCode'] = currency_code
        if customer_party:
            sale['CustomerParty'] = customer_party
        if extra:
            sale.update(extra)

        payload = {'TransactionHandle': self._transaction_handle(), 'Sale': sale}
        return self._check(self._post('CurrentSale', payload))

    # ------------------------------------------------------------------
    # 3. Satış Sorgu
    # ------------------------------------------------------------------

    def get_sale_result(self, sale_number=None, order_no=None, sale_id=None,
                        receipt_image=False, receipt_json=False, receipt_text=False):
        """Satış sonucu sorgula (GetSaleResult)."""
        sale = {}
        if sale_number:
            sale['SaleNumber'] = sale_number
        elif order_no:
            sale['OrderNo'] = order_no
        elif sale_id:
            sale['Id'] = sale_id
        else:
            raise PavoAPIError('GetSaleResult: SaleNumber, OrderNo veya Id gereklidir.')

        if receipt_image:
            sale['ReceiptImageEnabled'] = True
        if receipt_json:
            sale['ReceiptJsonEnabled'] = True
        if receipt_text:
            sale['ReceiptTextEnabled'] = True

        payload = {'TransactionHandle': self._transaction_handle(), 'Sale': sale}
        return self._check(self._post('GetSaleResult', payload))
