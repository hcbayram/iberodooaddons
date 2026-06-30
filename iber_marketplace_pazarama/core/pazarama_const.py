"""
Pazarama API sabit tanımlamaları.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
"""

PAZARAMA_API_BASE = 'https://isortagim.pazarama.com'

ORDER_STATUSES = [
    ('Created', 'Oluşturuldu'),
    ('Approved', 'Onaylandı'),
    ('Preparing', 'Hazırlanıyor'),
    ('ReadyForShipment', 'Kargoya Hazır'),
    ('Shipped', 'Kargoya Verildi'),
    ('Delivered', 'Teslim Edildi'),
    ('Cancelled', 'İptal Edildi'),
    ('Returned', 'İade Edildi'),
    ('UnDelivered', 'Teslim Edilemedi'),
]

CARGO_COMPANIES = [
    ('YURTICI_KARGO', 'Yurtiçi Kargo'),
    ('ARAS_KARGO', 'Aras Kargo'),
    ('MNG_KARGO', 'MNG Kargo'),
    ('PTT_KARGO', 'PTT Kargo'),
    ('SURAT_KARGO', 'Sürat Kargo'),
    ('SENDEO', 'Sendeo'),
    ('UPS_KARGO', 'UPS Kargo'),
    ('HOROZ_LOJISTIK', 'Horoz Lojistik'),
]
