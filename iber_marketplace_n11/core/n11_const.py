"""
N11 SOAP API sabit tanımlamaları.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
"""

N11_ORDER_SERVICE_URL = 'https://api.n11.com/ws/orderService'
N11_STOCK_SERVICE_URL = 'https://api.n11.com/ws/productStockService'
N11_SCHEMAS_NS = 'http://www.n11.com/ws/schemas'
N11_SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'

ORDER_STATUSES = [
    ('New', 'Yeni'),
    ('Approved', 'Onaylandı'),
    ('WaitingForShipment', 'Kargoya Hazır'),
    ('Shipped', 'Kargoya Verildi'),
    ('Delivered', 'Teslim Edildi'),
    ('Returned', 'İade'),
    ('Cancelled', 'İptal'),
    ('WaitingForSurrenderedGoods', 'Mal Teslimi Bekleniyor'),
    ('Refunded', 'İade Edildi'),
]

CARGO_COMPANIES = [
    ('ARAS_KARGO', 'Aras Kargo'),
    ('YURTICI_KARGO', 'Yurtiçi Kargo'),
    ('MNG_KARGO', 'MNG Kargo'),
    ('PTT_KARGO', 'PTT Kargo'),
    ('SURAT_KARGO', 'Sürat Kargo'),
    ('SENDEO', 'Sendeo'),
    ('UPS_KARGO', 'UPS Kargo'),
    ('HOROZ_LOJISTIK', 'Horoz Lojistik'),
]
