CICEKSEPETI_API_BASE = 'https://apis.ciceksepeti.com'

ORDER_STATUSES = [
    ('Created', 'Oluşturuldu'),
    ('Preparing', 'Hazırlanıyor'),
    ('Shipped', 'Kargoya Verildi'),
    ('Delivered', 'Teslim Edildi'),
    ('Cancelled', 'İptal Edildi'),
    ('Returned', 'İade Edildi'),
    ('UnDelivered', 'Teslim Edilemedi'),
    ('WaitingForSupplier', 'Tedarikçi Bekleniyor'),
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
    ('CICEK_SEPETI_LOJISTIK', 'Çiçeksepeti Lojistik'),
]
