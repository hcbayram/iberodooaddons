# -*- coding: utf-8 -*-
# NES Teknoloji entegratör varsayılan bağlantı bilgileri.
# Üretim bilgileri kurulum sonrası Yapılandırma → İntegratörler ekranından girilir.

INTEGRATOR_DEFAULTS = {
    "name": "NES Teknoloji",
    "code": "NES",
    "module_name": "iber_edonusum_nes",
    "is_test": True,

    # Test ortamı
    "test_base_url": "https://apitest.nes.com.tr",
    "test_username": "test01@nes.com.tr",
    "test_password": "V9zH7Hh55LIl",
    "test_apikey": "A22D724F127FB3BF22F60AD470F84F69429F2BCCD26F6097D1EAF6FC616D74C6",
    "test_token": "",

    # Üretim ortamı (kurulum sonrası doldurulur)
    "base_url": "https://api.nes.com.tr",
    "username": "",
    "password": "",
    "apikey": "",
    "token": "",
}
