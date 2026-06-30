# -*- coding: utf-8 -*-
# Hızlı Teknoloji entegratör varsayılan bağlantı bilgileri.
# Test bilgileri Postman koleksiyonundan alınmıştır.
# Üretim bilgileri kurulum sonrası Yapılandırma → İntegratörler ekranından girilir.

import json

INTEGRATOR_DEFAULTS = {
    "name": "Hızlı Teknoloji",
    "code": "HIZLI",
    "module_name": "iber_edonusum_hizli",
    "is_test": True,

    # Test ortamı
    "test_base_url": "https://econnecttest.hizliteknoloji.com.tr/HizliApi/RestApi",
    "test_username": "hizlitest",
    "test_password": "aOw873JRxb",
    "test_apikey": "",
    "test_token": "",

    # Üretim ortamı (kurulum sonrası doldurulur)
    "base_url": "https://econnect.hizliteknoloji.com.tr/HizliApi/RestApi",
    "username": "",
    "password": "",
    "apikey": "",
    "token": "",

    # Entegratöre özgü alanlar extra JSON'da tutulur
    "extra": json.dumps({
        "test_secretkey": "",   # UtilEncrypt adımı için — kurulum sonrası girilir
        "secretkey": "",
    }),
}
