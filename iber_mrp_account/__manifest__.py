{
    "name": "İberoDoo Üretim Maliyet Hesapları (711/721/731)",
    "version": "19.0.1.0.0",
    "category": "Manufacturing/Accounting",
    "author": "Algebrasoft",
    "summary": "Üretim emirlerinde 711 ara hesabını kullanır ve MO tamamlandığında 151'e yansıtır",
    "description": """
        TEKDÜZEN 7/A maliyet akışı:

          1. Hammadde tüketimi : DR 711 / CR 150  (ürün kategorisindeki 711 hesabından)
          2. MO tamamlandığında: DR 151 / CR 711  (otomatik yansıtma girişi)
          3. İşçilik (WC)      : DR 151 / CR 721  (iş merkezi expense_account_id = 721)
          4. GÜG (WC)          : DR 151 / CR 731  (iş merkezi expense_account_id = 731)
          5. Mamul girişi      : DR 152 / CR 151  (standart Odoo — değişmez)

        Notlar:
          - 721 ve 731 yansıtmaları standart mrp_account _post_labour ile yapılır;
            iş merkezindeki expense_account_id'yi 721 veya 731 olarak ayarlamak yeterlidir.
          - 711 atanmamış ürün kategorilerindeki hareketler standart akışa (DR 151 / CR 150) döner.
    """,
    "depends": ["mrp_account"],
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/product_category_views.xml",
        "views/mrp_workcenter_views.xml",
        "views/mrp_production_views.xml",
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
