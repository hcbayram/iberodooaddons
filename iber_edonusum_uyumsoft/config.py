# -*- coding: utf-8 -*-
# Uyumsoft entegratör varsayılan bağlantı bilgileri.
#
# Test URL'i firmanın 2026-08-07'de bildirdiği gerçek adrestir:
#   https://efaturaws-test.uyum.com.tr/Services/Integration (SOAP, WSDL doğrulandı)
# Üretim URL'i tahminen "-test" kaldırılarak türetilmiştir — firmayla TEYİT EDİLMELİ.
#
# test_username/test_password = "Uyumsoft"/"Uyumsoft" (elde bulunan tek bilgi).
# NOT: Bu bilgiyle daha önce denenen canlı bir WhoAmI çağrısı sunucudan
# "a:InvalidSecurity" SOAP Fault döndürmüştü (zarf kabul edildi, kimlik bilgisi
# geçersiz) — firmadan gerçek test kullanıcı adı/şifresi alınınca güncellenmeli.
# Üretim bilgileri kurulum sonrası Yapılandırma → Entegratörler ekranından girilir.

INTEGRATOR_DEFAULTS = {
    "name": "Uyumsoft",
    "code": "UYUMSOFT",
    "module_name": "iber_edonusum_uyumsoft",
    "is_test": True,

    # Test ortamı
    "test_base_url": "https://efaturaws-test.uyum.com.tr",
    "test_username": "Uyumsoft",
    "test_password": "Uyumsoft",
    "test_apikey": "",
    "test_token": "",

    # Üretim ortamı (kurulum sonrası doldurulur — Uyumsoft'tan alınan gerçek
    # kullanıcı bilgileri girilmeden gönderim yapılamaz)
    "base_url": "https://efaturaws.uyum.com.tr",
    "username": "",
    "password": "",
    "apikey": "",
    "token": "",
}
