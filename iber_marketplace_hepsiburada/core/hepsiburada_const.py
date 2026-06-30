"""
Hepsiburada API sabit tanımlamaları.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
"""

MPOP_API_BASE = 'https://mpop.hepsiburada.com'
LISTING_API_BASE = 'https://listing-external.hepsiburada.com'

ORDER_STATUSES = [
    ('New', 'Yeni'),
    ('Processing', 'İşleniyor'),
    ('Shipping', 'Kargoya Hazır'),
    ('Shipped', 'Kargoya Verildi'),
    ('Delivered', 'Teslim Edildi'),
    ('UnDelivered', 'Teslim Edilemedi'),
    ('Returned', 'İade'),
    ('Cancelled', 'İptal'),
    ('WaitingForPayment', 'Ödeme Bekleniyor'),
]

CARGO_COMPANIES = [
    ('YURTICI_KARGO', 'Yurtiçi Kargo'),
    ('ARAS_KARGO', 'Aras Kargo'),
    ('MNG_KARGO', 'MNG Kargo'),
    ('PTT_KARGO', 'PTT Kargo'),
    ('SURAT_KARGO', 'Sürat Kargo'),
    ('SENDEO', 'Sendeo'),
    ('HOROZ_LOJISTIK', 'Horoz Lojistik'),
    ('UPS_KARGO', 'UPS Kargo'),
    ('BORUSAN_LOJISTIK', 'Borusan Lojistik'),
    ('HB_LOJISTIK', 'HB Lojistik'),
]
