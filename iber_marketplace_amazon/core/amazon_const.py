AMAZON_LWA_TOKEN_URL = 'https://api.amazon.com/auth/o2/token'
AMAZON_API_BASE = 'https://sellingpartnerapi-eu.amazon.com'
AMAZON_MARKETPLACE_ID = 'A33AVAJ2PDY3EV'  # Amazon.com.tr

ORDER_STATUSES = [
    ('Pending', 'Beklemede'),
    ('Unshipped', 'Kargoya Verilmedi'),
    ('PartiallyShipped', 'Kısmen Kargoya Verildi'),
    ('Shipped', 'Kargoya Verildi'),
    ('InvoiceUnconfirmed', 'Fatura Onaylanmadı'),
    ('Canceled', 'İptal Edildi'),
    ('Unfulfillable', 'Teslim Edilemez'),
]

CARRIER_CODES = [
    ('YURTICI_KARGO', 'Yurtiçi Kargo'),
    ('ARAS_KARGO', 'Aras Kargo'),
    ('MNG_KARGO', 'MNG Kargo'),
    ('PTT_KARGO', 'PTT Kargo'),
    ('SURAT_KARGO', 'Sürat Kargo'),
    ('UPS', 'UPS'),
    ('FEDEX', 'FedEx'),
    ('DHL', 'DHL'),
    ('Other', 'Diğer'),
]

FEED_TYPE_INVENTORY = 'POST_INVENTORY_AVAILABILITY_DATA'
FEED_TYPE_PRICE = 'POST_PRODUCT_PRICING_DATA'
