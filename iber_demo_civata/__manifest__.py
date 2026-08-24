{
    'name': 'Demo Verisi: Civata & Bağlantı Elemanı Üretimi',
    'version': '19.0.1.0.0',
    'summary': 'Otomotiv/İnşaat/Tarım/Demiryolu sektörlerine hizmet veren bir civata üreticisi için '
               'uçtan uca Odoo 19 Enterprise tanıtım senaryosu — müşteriler, ürünler, BOM, iş merkezleri, '
               'tedarikçiler, fiyat listesi, lot stokları, kalite kontrol noktaları, CRM fırsatları, '
               'satış siparişi ve üretim emri.',
    'description': """
Civata & Bağlantı Elemanı Üretimi — Odoo 19 Demo Verisi
=========================================================
MAXTECH Bağlantı A.Ş. senaryosu için hazırlanmış, saf veri (data-only) demo modülüdür.
BMW Werk Leipzig'in M8×30 DIN 931 8.8 civata siparişini hammaddeden sevkiyata kadar
canlı göstermek için gereken tüm referans verileri kurulum anında yükler:

* 5 müşteri (BMW, Liebherr, CLAAS, Deutsche Bahn, Nordex) + 3 çelik tedarikçisi
* 5 mamul civata/vida + 4 hammadde/sarf bileşeni
* M8×30 için BOM ve 7 istasyonlu üretim rotası (WC-001 … WC-007)
* Tedarikçi fiyat karşılaştırması ve "OEM Premium" miktar kademeli fiyat listesi
* Lot numaralı hammadde stoğu + mamul başlangıç stokları
* M8×30 rotası için 5 kalite kontrol noktası ve örnek bir kalite uyarısı
* CRM satış hunisi (5 fırsat), BMW için hazır teklif (SO-2026-0847) ve üretim emri (MO-2026-0312)

Bu modül Odoo Enterprise'a özel Shop Floor (mrp_workorder) ve Quality (quality_control)
uygulamalarına bağımlıdır.
    """,
    'author': 'Iber Bilisim',
    'website': 'https://www.iberbilisim.com.tr',
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'depends': [
        'product',
        'stock',
        'purchase',
        'sale_management',
        'crm',
        'mrp',
        'mrp_workorder',
        'quality_control',
    ],
    'data': [
        'data/01_res_partner.xml',
        'data/02_product_category.xml',
        'data/03_product_product.xml',
        'data/04_product_supplierinfo.xml',
        'data/05_product_pricelist.xml',
        'data/06_mrp_workcenter.xml',
        'data/07_mrp_bom.xml',
        'data/08_stock_lot_quant.xml',
        'data/09_quality_point.xml',
        'data/10_quality_alert.xml',
        'data/11_crm_lead.xml',
        'data/12_sale_order.xml',
        'data/13_mrp_production.xml',
    ],
    'installable': True,
    'application': False,
}
