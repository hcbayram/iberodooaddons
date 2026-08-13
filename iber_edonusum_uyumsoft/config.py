# -*- coding: utf-8 -*-
# Uyumsoft entegratör varsayılan bağlantı bilgileri.
#
# Test URL'i firmanın 2026-08-07'de bildirdiği gerçek adrestir:
#   https://efaturaws-test.uyum.com.tr/Services/Integration (SOAP, WSDL doğrulandı)
# Üretim URL'i tahminen "-test" kaldırılarak türetilmiştir — firmayla TEYİT EDİLMELİ.
#
# test_username/test_password HENÜZ GERÇEK DEĞİL: elde bulunan "Uyumsoft/Uyumsoft"
# bilgisiyle canlı bir WhoAmI çağrısı denendi, sunucu "a:InvalidSecurity" SOAP
# Fault döndürdü (zarf kabul edildi, kimlik bilgisi geçersiz). Firmadan gerçek
# test kullanıcı adı/şifresi alınınca burası güncellenmeli.
# Üretim bilgileri kurulum sonrası Yapılandırma → Entegratörler ekranından girilir.

INTEGRATOR_DEFAULTS = {
    "name": "Uyumsoft",
    "code": "UYUMSOFT",
    "module_name": "iber_edonusum_uyumsoft",
    "is_test": True,

    # Test ortamı
    "test_base_url": "https://efaturaws-test.uyum.com.tr",
    "test_username": "",
    "test_password": "",
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
