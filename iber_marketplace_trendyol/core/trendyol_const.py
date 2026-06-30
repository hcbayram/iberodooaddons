"""
Trendyol API sabit tanımlamaları.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
"""

TRENDYOL_API_BASE = 'https://api.trendyol.com/sapigw'

ORDER_STATUSES = [
    ('Created', 'Oluşturuldu'),
    ('Picking', 'Hazırlanıyor'),
    ('Invoiced', 'Faturalandı'),
    ('Shipped', 'Kargoya Verildi'),
    ('Delivered', 'Teslim Edildi'),
    ('UnDelivered', 'Teslim Edilemedi'),
    ('Returned', 'İade Edildi'),
    ('Cancelled', 'İptal Edildi'),
]

CARGO_COMPANIES = [
    ('YURTICI_KARGO', 'Yurtiçi Kargo'),
    ('ARAS_KARGO', 'Aras Kargo'),
    ('MNG_KARGO', 'MNG Kargo'),
    ('PTT_KARGO', 'PTT Kargo'),
    ('UPS_KARGO', 'UPS Kargo'),
    ('HOROZ_LOJISTIK', 'Horoz Lojistik'),
    ('SURAT_KARGO', 'Sürat Kargo'),
    ('BORUSAN_LOJISTIK', 'Borusan Lojistik'),
    ('SENDEO', 'Sendeo'),
    ('DHL', 'DHL'),
    ('FEDEX', 'FedEx'),
]

# Trendyol kargo sağlayıcı ID eşleşmesi
CARGO_PROVIDER_IDS = {
    'YURTICI_KARGO': 1,
    'ARAS_KARGO': 2,
    'MNG_KARGO': 3,
    'PTT_KARGO': 4,
    'UPS_KARGO': 5,
    'HOROZ_LOJISTIK': 20,
    'SURAT_KARGO': 6,
    'BORUSAN_LOJISTIK': 12,
    'SENDEO': 25,
    'DHL': 10,
    'FEDEX': 11,
}
