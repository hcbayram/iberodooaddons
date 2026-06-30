"""
PttAVM API sabit tanımlamaları.
Bu modül Odoo bağımlılığı içermez — core/ katmanında tutulur.
"""

PTTAVM_API_BASE = 'https://www.pttavm.com/api'

ORDER_STATUSES = [
    ('WaitingForApproval', 'Onay Bekleniyor'),
    ('Approved', 'Onaylandı'),
    ('Preparing', 'Hazırlanıyor'),
    ('ReadyForShipment', 'Kargoya Hazır'),
    ('Shipped', 'Kargoya Verildi'),
    ('Delivered', 'Teslim Edildi'),
    ('Returned', 'İade'),
    ('Cancelled', 'İptal'),
    ('UnDelivered', 'Teslim Edilemedi'),
]

CARGO_COMPANIES = [
    ('PTT_KARGO', 'PTT Kargo'),
    ('YURTICI_KARGO', 'Yurtiçi Kargo'),
    ('ARAS_KARGO', 'Aras Kargo'),
    ('MNG_KARGO', 'MNG Kargo'),
    ('SURAT_KARGO', 'Sürat Kargo'),
    ('SENDEO', 'Sendeo'),
    ('UPS_KARGO', 'UPS Kargo'),
    ('HOROZ_LOJISTIK', 'Horoz Lojistik'),
]
