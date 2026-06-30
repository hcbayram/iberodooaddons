import re
import xml.etree.ElementTree as ET
import requests
from xml.sax.saxutils import escape as xml_escape

SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
TEMPURI = 'http://tempuri.org/'


class TicimaxError(Exception):
    def __init__(self, message, fault_code=None, detail=None):
        super().__init__(message)
        self.fault_code = fault_code
        self.detail = detail


def _strip_ns(tag):
    return re.sub(r'\{[^}]+\}', '', tag)


def _elem_to_dict(elem):
    children = list(elem)
    if not children:
        return (elem.text or '').strip()
    result = {}
    for child in children:
        key = _strip_ns(child.tag)
        val = _elem_to_dict(child)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(val)
        else:
            result[key] = val
    return result


def _ensure_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _bool_xml(val):
    return 'true' if val else 'false'


class TicimaxClient:
    """
    Ticimax SOAP web servis istemcisi.
    Odoo'ya bağımlılık yoktur; core/ katmanında tutulur.

    base_url: örn. https://www.siteadi.com
    uye_kodu: Ticimax servis şifresi
    timeout: HTTP istek zaman aşımı (saniye)
    """

    def __init__(self, base_url, uye_kodu, timeout=30):
        self.base_url = base_url.rstrip('/')
        self.uye_kodu = uye_kodu
        self.timeout = timeout

    # ------------------------------------------------------------------
    # HTTP / SOAP altyapı
    # ------------------------------------------------------------------

    def _service_url(self, service_name):
        return f'{self.base_url}/Servis/{service_name}.svc'

    def _soap_action(self, interface_name, method_name):
        return f'{TEMPURI}{interface_name}/{method_name}'

    def _wrap_envelope(self, body_xml):
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            '<s:Body>'
            f'{body_xml}'
            '</s:Body>'
            '</s:Envelope>'
        )

    def _call(self, service_name, interface_name, method_name, body_xml):
        url = self._service_url(service_name)
        soap_action = self._soap_action(interface_name, method_name)
        envelope = self._wrap_envelope(body_xml)
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': f'"{soap_action}"',
        }
        try:
            resp = requests.post(url, data=envelope.encode('utf-8'),
                                 headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TicimaxError(f'HTTP bağlantı hatası: {exc}')

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            raise TicimaxError(f'SOAP yanıt ayrıştırma hatası: {exc}')

        # SOAP Fault kontrolü
        fault = root.find('.//{%s}Fault' % SOAP_NS)
        if fault is not None:
            code_el = fault.find('faultcode')
            str_el = fault.find('faultstring')
            code = code_el.text if code_el is not None else ''
            msg = str_el.text if str_el is not None else resp.text
            raise TicimaxError(f'SOAP Fault [{code}]: {msg}', fault_code=code)

        if not resp.ok:
            raise TicimaxError(f'HTTP {resp.status_code}: {resp.text[:500]}')

        # Yanıt body'sini döndür (namespace'leri soyulmuş dict)
        body = root.find('.//{%s}Body' % SOAP_NS)
        if body is None:
            return {}
        children = list(body)
        if not children:
            return {}
        return _elem_to_dict(children[0])

    # ------------------------------------------------------------------
    # 1. UrunServis
    # ------------------------------------------------------------------

    def select_kategori(self, kategori_id=0):
        """Tüm kategorileri veya tekil kategori bilgisini döndürür."""
        body = (
            f'<SelectKategori xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'<kategoriID>{int(kategori_id)}</kategoriID>'
            '</SelectKategori>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SelectKategori', body)
        return _ensure_list(result.get('SelectKategoriResult', {}).get('Kategori'))

    def save_kategori(self, id=0, pid=0, aktif=True, tanim='', kod='',
                      seo_anahtar_kelime='', seo_sayfa_aciklama='', seo_sayfa_baslik=''):
        """Yeni kategori ekler veya mevcut kategoriyi günceller. Kategori ID döner."""
        body = (
            f'<SaveKategori xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<kategori>'
            f'<ID>{int(id)}</ID>'
            f'<PID>{int(pid)}</PID>'
            f'<Aktif>{_bool_xml(aktif)}</Aktif>'
            f'<Tanim>{xml_escape(str(tanim))}</Tanim>'
            f'<Kod>{xml_escape(str(kod))}</Kod>'
            f'<SeoAnahtarKelime>{xml_escape(str(seo_anahtar_kelime))}</SeoAnahtarKelime>'
            f'<SeoSayfaAciklama>{xml_escape(str(seo_sayfa_aciklama))}</SeoSayfaAciklama>'
            f'<SeoSayfaBaslik>{xml_escape(str(seo_sayfa_baslik))}</SeoSayfaBaslik>'
            '</kategori>'
            '</SaveKategori>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SaveKategori', body)
        return result.get('SaveKategoriResult', '')

    def select_marka(self, marka_id=0):
        """Tüm markaları veya tekil marka bilgisini döndürür."""
        body = (
            f'<SelectMarka xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'<markaID>{int(marka_id)}</markaID>'
            '</SelectMarka>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SelectMarka', body)
        return _ensure_list(result.get('SelectMarkaResult', {}).get('Marka'))

    def save_marka(self, id=0, aktif=True, tanim='',
                   seo_anahtar_kelime='', seo_sayfa_aciklama='', seo_sayfa_baslik=''):
        body = (
            f'<SaveMarka xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<marka>'
            f'<ID>{int(id)}</ID>'
            f'<Aktif>{_bool_xml(aktif)}</Aktif>'
            f'<Tanim>{xml_escape(str(tanim))}</Tanim>'
            f'<SeoAnahtarKelime>{xml_escape(str(seo_anahtar_kelime))}</SeoAnahtarKelime>'
            f'<SeoSayfaAciklama>{xml_escape(str(seo_sayfa_aciklama))}</SeoSayfaAciklama>'
            f'<SeoSayfaBaslik>{xml_escape(str(seo_sayfa_baslik))}</SeoSayfaBaslik>'
            '</marka>'
            '</SaveMarka>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SaveMarka', body)
        return result.get('SaveMarkaResult', '')

    def select_tedarikci(self, tedarikci_id=0):
        body = (
            f'<SelectTedarikci xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'<tedarikciID>{int(tedarikci_id)}</tedarikciID>'
            '</SelectTedarikci>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SelectTedarikci', body)
        return _ensure_list(result.get('SelectTedarikciResult', {}).get('Tedarikci'))

    def save_tedarikci(self, id=0, aktif=True, tanim='', mail='', not_=''):
        body = (
            f'<SaveTedarikci xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<tedarikci>'
            f'<ID>{int(id)}</ID>'
            f'<Aktif>{_bool_xml(aktif)}</Aktif>'
            f'<Tanim>{xml_escape(str(tanim))}</Tanim>'
            f'<Mail>{xml_escape(str(mail))}</Mail>'
            f'<Not>{xml_escape(str(not_))}</Not>'
            '</tedarikci>'
            '</SaveTedarikci>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SaveTedarikci', body)
        return result.get('SaveTedarikciResult', '')

    def select_para_birimi(self, para_birimi_id=0):
        body = (
            f'<SelectParaBirimi xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'<ParaBirimiID>{int(para_birimi_id)}</ParaBirimiID>'
            '</SelectParaBirimi>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SelectParaBirimi', body)
        return _ensure_list(result.get('SelectParaBirimiResult', {}).get('ParaBirimi'))

    def save_para_birimi(self, id=0, aktif=True, tanim='', doviz_kodu='', kur=1.0):
        body = (
            f'<SaveParaBirimi xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<parabirimi>'
            f'<ID>{int(id)}</ID>'
            f'<Aktif>{_bool_xml(aktif)}</Aktif>'
            f'<Tanim>{xml_escape(str(tanim))}</Tanim>'
            f'<DovizKodu>{xml_escape(str(doviz_kodu))}</DovizKodu>'
            f'<Kur>{float(kur)}</Kur>'
            '</parabirimi>'
            '</SaveParaBirimi>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SaveParaBirimi', body)
        return result.get('SaveParaBirimiResult', '')

    def select_urun(self, filtre=None, sayfalama=None):
        """
        filtre: dict — Aktif, Firsat, Indirimli, Vitrin (-1/0/1), KategoriID, MarkaID,
                       UrunKartiID, EntegrasyonDegerTanim, EntegrasyonKodu
        sayfalama: dict — BaslangicIndex, KayitSayisi, SiralamaDegeri, SiralamaYonu
        """
        filtre = filtre or {}
        sayfalama = sayfalama or {}

        def _fval(key, default):
            return filtre.get(key, default)

        filtre_xml = (
            '<f>'
            f'<Aktif>{int(_fval("Aktif", -1))}</Aktif>'
            f'<Firsat>{int(_fval("Firsat", -1))}</Firsat>'
            f'<Indirimli>{int(_fval("Indirimli", -1))}</Indirimli>'
            f'<Vitrin>{int(_fval("Vitrin", -1))}</Vitrin>'
            f'<KategoriID>{int(_fval("KategoriID", 0))}</KategoriID>'
            f'<MarkaID>{int(_fval("MarkaID", 0))}</MarkaID>'
            f'<UrunKartiID>{int(_fval("UrunKartiID", 0))}</UrunKartiID>'
        )
        if _fval('EntegrasyonDegerTanim', ''):
            filtre_xml += (
                f'<EntegrasyonDegerTanim>{xml_escape(str(_fval("EntegrasyonDegerTanim", "")))}</EntegrasyonDegerTanim>'
                f'<EntegrasyonKodu>{xml_escape(str(_fval("EntegrasyonKodu", "")))}</EntegrasyonKodu>'
            )
        filtre_xml += '</f>'

        sayfalama_xml = (
            '<s>'
            f'<BaslangicIndex>{int(sayfalama.get("BaslangicIndex", 0))}</BaslangicIndex>'
            f'<KayitSayisi>{int(sayfalama.get("KayitSayisi", 100))}</KayitSayisi>'
            f'<SiralamaDegeri>{xml_escape(str(sayfalama.get("SiralamaDegeri", "ID")))}</SiralamaDegeri>'
            f'<SiralamaYonu>{xml_escape(str(sayfalama.get("SiralamaYonu", "ASC")))}</SiralamaYonu>'
            '</s>'
        )
        body = (
            f'<SelectUrun xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'{filtre_xml}'
            f'{sayfalama_xml}'
            '</SelectUrun>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SelectUrun', body)
        return _ensure_list(result.get('SelectUrunResult', {}).get('UrunKarti'))

    def select_urun_count(self, filtre=None):
        filtre = filtre or {}

        def _fval(key, default):
            return filtre.get(key, default)

        filtre_xml = (
            '<f>'
            f'<Aktif>{int(_fval("Aktif", -1))}</Aktif>'
            f'<Firsat>{int(_fval("Firsat", -1))}</Firsat>'
            f'<Indirimli>{int(_fval("Indirimli", -1))}</Indirimli>'
            f'<Vitrin>{int(_fval("Vitrin", -1))}</Vitrin>'
            f'<KategoriID>{int(_fval("KategoriID", 0))}</KategoriID>'
            f'<MarkaID>{int(_fval("MarkaID", 0))}</MarkaID>'
            f'<UrunKartiID>{int(_fval("UrunKartiID", 0))}</UrunKartiID>'
            '</f>'
        )
        body = (
            f'<SelectUrunCount xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'{filtre_xml}'
            '</SelectUrunCount>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SelectUrunCount', body)
        try:
            return int(result.get('SelectUrunCountResult', 0))
        except (TypeError, ValueError):
            return 0

    def save_urun(self, urun_kartlari, urun_karti_ayar=None, varyasyon_ayar=None):
        """
        urun_kartlari: list of dict — UrunKarti alanları
        urun_karti_ayar: dict — UrunKartiAyar boolean alanları
        varyasyon_ayar: dict — VaryasyonAyar boolean alanları
        Dönen değer: güncel urun_kartlari listesi (ref parametresi)
        """
        urun_karti_ayar = urun_karti_ayar or {}
        varyasyon_ayar = varyasyon_ayar or {}

        def _ayar(d, key, default=True):
            return _bool_xml(d.get(key, default))

        kartlar_xml = ''
        for k in urun_kartlari:
            kategoriler_xml = ''.join(
                f'<int>{int(kid)}</int>' for kid in (k.get('Kategoriler') or [])
            )
            resimler_xml = ''.join(
                f'<string>{xml_escape(str(r))}</string>' for r in (k.get('Resimler') or [])
            )
            varyasyonlar_xml = ''
            for v in (k.get('Varyasyonlar') or []):
                ozellikler_xml = ''.join(
                    f'<VaryasyonOzellik>'
                    f'<Tanim>{xml_escape(str(o.get("Tanim", "")))}</Tanim>'
                    f'<Deger>{xml_escape(str(o.get("Deger", "")))}</Deger>'
                    '</VaryasyonOzellik>'
                    for o in (v.get('Ozellikler') or [])
                )
                v_resimler_xml = ''.join(
                    f'<string>{xml_escape(str(r))}</string>' for r in (v.get('Resimler') or [])
                )
                varyasyonlar_xml += (
                    '<Varyasyon>'
                    f'<ID>{int(v.get("ID", 0))}</ID>'
                    f'<Aktif>{_bool_xml(v.get("Aktif", True))}</Aktif>'
                    f'<AlisFiyati>{float(v.get("AlisFiyati", 0))}</AlisFiyati>'
                    f'<Barkod>{xml_escape(str(v.get("Barkod", "")))}</Barkod>'
                    f'<Desi>{float(v.get("Desi", 0))}</Desi>'
                    f'<KargoUcreti>{float(v.get("KargoUcreti", 0))}</KargoUcreti>'
                    f'<KdvDahil>{_bool_xml(v.get("KdvDahil", False))}</KdvDahil>'
                    f'<KdvOrani>{float(v.get("KdvOrani", 18))}</KdvOrani>'
                    f'<Ozellikler>{ozellikler_xml}</Ozellikler>'
                    f'<ParaBirimiID>{int(v.get("ParaBirimiID", 1))}</ParaBirimiID>'
                    f'<Resimler>{v_resimler_xml}</Resimler>'
                    f'<SatisFiyati>{float(v.get("SatisFiyati", 0))}</SatisFiyati>'
                    f'<StokAdedi>{int(v.get("StokAdedi", 0))}</StokAdedi>'
                    f'<StokKodu>{xml_escape(str(v.get("StokKodu", "")))}</StokKodu>'
                    '</Varyasyon>'
                )

            kartlar_xml += (
                '<UrunKarti>'
                f'<ID>{int(k.get("ID", 0))}</ID>'
                f'<Aktif>{_bool_xml(k.get("Aktif", True))}</Aktif>'
                f'<UrunAdi>{xml_escape(str(k.get("UrunAdi", "")))}</UrunAdi>'
                f'<Aciklama>{xml_escape(str(k.get("Aciklama", "")))}</Aciklama>'
                f'<AnaKategori>{xml_escape(str(k.get("AnaKategori", "")))}</AnaKategori>'
                f'<AnaKategoriID>{int(k.get("AnaKategoriID", 0))}</AnaKategoriID>'
                f'<Kategoriler>{kategoriler_xml}</Kategoriler>'
                f'<MarkaID>{int(k.get("MarkaID", 0))}</MarkaID>'
                f'<TedarikciID>{int(k.get("TedarikciID", 0))}</TedarikciID>'
                f'<Resimler>{resimler_xml}</Resimler>'
                f'<SatisBirimi>{xml_escape(str(k.get("SatisBirimi", "Adet")))}</SatisBirimi>'
                f'<UcretsizKargo>{_bool_xml(k.get("UcretsizKargo", False))}</UcretsizKargo>'
                f'<OnYazi>{xml_escape(str(k.get("OnYazi", "")))}</OnYazi>'
                f'<PuanDeger>{int(k.get("PuanDeger", 0))}</PuanDeger>'
                f'<SeoAnahtarKelime>{xml_escape(str(k.get("SeoAnahtarKelime", "")))}</SeoAnahtarKelime>'
                f'<SeoSayfaAciklama>{xml_escape(str(k.get("SeoSayfaAciklama", "")))}</SeoSayfaAciklama>'
                f'<SeoSayfaBaslik>{xml_escape(str(k.get("SeoSayfaBaslik", "")))}</SeoSayfaBaslik>'
                f'<Varyasyonlar>{varyasyonlar_xml}</Varyasyonlar>'
                f'<Vitrin>{_bool_xml(k.get("Vitrin", False))}</Vitrin>'
                f'<YeniUrun>{_bool_xml(k.get("YeniUrun", False))}</YeniUrun>'
                '</UrunKarti>'
            )

        uk_ayar_xml = (
            '<ukAyar>'
            f'<AciklamaGuncelle>{_ayar(urun_karti_ayar, "AciklamaGuncelle")}</AciklamaGuncelle>'
            f'<AktifGuncelle>{_ayar(urun_karti_ayar, "AktifGuncelle")}</AktifGuncelle>'
            f'<FBStoreGosterGuncelle>{_ayar(urun_karti_ayar, "FBStoreGosterGuncelle", False)}</FBStoreGosterGuncelle>'
            f'<FirsatUrunuGuncelle>{_ayar(urun_karti_ayar, "FirsatUrunuGuncelle")}</FirsatUrunuGuncelle>'
            f'<KategoriGuncelle>{_ayar(urun_karti_ayar, "KategoriGuncelle")}</KategoriGuncelle>'
            f'<MaksTaksitSayisiGuncelle>{_ayar(urun_karti_ayar, "MaksTaksitSayisiGuncelle", False)}</MaksTaksitSayisiGuncelle>'
            f'<MarkaGuncelle>{_ayar(urun_karti_ayar, "MarkaGuncelle")}</MarkaGuncelle>'
            f'<OnYaziGuncelle>{_ayar(urun_karti_ayar, "OnYaziGuncelle", False)}</OnYaziGuncelle>'
            f'<ParaPuanGuncelle>{_ayar(urun_karti_ayar, "ParaPuanGuncelle")}</ParaPuanGuncelle>'
            f'<SatisBirimiGuncelle>{_ayar(urun_karti_ayar, "SatisBirimiGuncelle", False)}</SatisBirimiGuncelle>'
            f'<SeoAnahtarKelimeGuncelle>{_ayar(urun_karti_ayar, "SeoAnahtarKelimeGuncelle", False)}</SeoAnahtarKelimeGuncelle>'
            f'<SeoSayfaAciklamaGuncelle>{_ayar(urun_karti_ayar, "SeoSayfaAciklamaGuncelle", False)}</SeoSayfaAciklamaGuncelle>'
            f'<SeoSayfaBaslikGuncelle>{_ayar(urun_karti_ayar, "SeoSayfaBaslikGuncelle", False)}</SeoSayfaBaslikGuncelle>'
            f'<TedarikciGuncelle>{_ayar(urun_karti_ayar, "TedarikciGuncelle", False)}</TedarikciGuncelle>'
            f'<UcretsizKargoGuncelle>{_ayar(urun_karti_ayar, "UcretsizKargoGuncelle")}</UcretsizKargoGuncelle>'
            f'<UrunAdiGuncelle>{_ayar(urun_karti_ayar, "UrunAdiGuncelle")}</UrunAdiGuncelle>'
            f'<UrunResimGuncelle>{_ayar(urun_karti_ayar, "UrunResimGuncelle", False)}</UrunResimGuncelle>'
            f'<VitrinGuncelle>{_ayar(urun_karti_ayar, "VitrinGuncelle", False)}</VitrinGuncelle>'
            f'<YeniUrunGuncelle>{_ayar(urun_karti_ayar, "YeniUrunGuncelle")}</YeniUrunGuncelle>'
            '</ukAyar>'
        )
        v_ayar_xml = (
            '<vAyar>'
            f'<AktifGuncelle>{_ayar(varyasyon_ayar, "AktifGuncelle", False)}</AktifGuncelle>'
            f'<AlisFiyatiGuncelle>{_ayar(varyasyon_ayar, "AlisFiyatiGuncelle")}</AlisFiyatiGuncelle>'
            f'<BarkodGuncelle>{_ayar(varyasyon_ayar, "BarkodGuncelle", False)}</BarkodGuncelle>'
            f'<IndirimliGuncelle>{_ayar(varyasyon_ayar, "IndirimliGuncelle")}</IndirimliGuncelle>'
            f'<KargoUcretiGuncelle>{_ayar(varyasyon_ayar, "KargoUcretiGuncelle", False)}</KargoUcretiGuncelle>'
            f'<KargoAgirligiGuncelle>{_ayar(varyasyon_ayar, "KargoAgirligiGuncelle")}</KargoAgirligiGuncelle>'
            f'<ParaBirimiGuncelle>{_ayar(varyasyon_ayar, "ParaBirimiGuncelle", False)}</ParaBirimiGuncelle>'
            f'<PiyasaFiyatiGuncelle>{_ayar(varyasyon_ayar, "PiyasaFiyatiGuncelle")}</PiyasaFiyatiGuncelle>'
            f'<SatisFiyatiGuncelle>{_ayar(varyasyon_ayar, "SatisFiyatiGuncelle", False)}</SatisFiyatiGuncelle>'
            f'<StokAdediGuncelle>{_ayar(varyasyon_ayar, "StokAdediGuncelle")}</StokAdediGuncelle>'
            f'<UyeTipiFiyat1Guncelle>{_ayar(varyasyon_ayar, "UyeTipiFiyat1Guncelle", False)}</UyeTipiFiyat1Guncelle>'
            f'<UyeTipiFiyat2Guncelle>{_ayar(varyasyon_ayar, "UyeTipiFiyat2Guncelle")}</UyeTipiFiyat2Guncelle>'
            f'<UyeTipiFiyat3Guncelle>{_ayar(varyasyon_ayar, "UyeTipiFiyat3Guncelle", False)}</UyeTipiFiyat3Guncelle>'
            f'<UyeTipiFiyat4Guncelle>{_ayar(varyasyon_ayar, "UyeTipiFiyat4Guncelle")}</UyeTipiFiyat4Guncelle>'
            f'<UyeTipiFiyat5Guncelle>{_ayar(varyasyon_ayar, "UyeTipiFiyat5Guncelle", False)}</UyeTipiFiyat5Guncelle>'
            f'<TedarikciKodunaGoreGuncelle>{_ayar(varyasyon_ayar, "TedarikciKodunaGoreGuncelle", False)}</TedarikciKodunaGoreGuncelle>'
            '</vAyar>'
        )
        body = (
            f'<SaveUrun xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'<urunKartlari>{kartlar_xml}</urunKartlari>'
            f'{uk_ayar_xml}'
            f'{v_ayar_xml}'
            '</SaveUrun>'
        )
        result = self._call('UrunServis', 'IUrunServis', 'SaveUrun', body)
        return _ensure_list(result.get('urunKartlari', {}).get('UrunKarti'))

    # ------------------------------------------------------------------
    # 2. SiparisServis
    # ------------------------------------------------------------------

    def select_siparis(self, filtre=None, sayfalama=None):
        """
        filtre: dict — EntegrasyonAktarildi, OdemeDurumu, OdemeTipi, SiparisDurumu,
                       SiparisID, SiparisTarihBas, SiparisTarihSon, UyeID,
                       EntegrasyonParams (dict: EntegrasyonKodu, Tanim)
        sayfalama: dict — BaslangicIndex, KayitSayisi, SiralamaDegeri, SiralamaYonu
        """
        filtre = filtre or {}
        sayfalama = sayfalama or {}

        entegrasyon_params = filtre.get('EntegrasyonParams', {})
        ep_xml = ''
        if entegrasyon_params:
            ep_xml = (
                '<EntegrasyonParams>'
                f'<EntegrasyonKodu>{xml_escape(str(entegrasyon_params.get("EntegrasyonKodu", "")))}</EntegrasyonKodu>'
                f'<Tanim>{xml_escape(str(entegrasyon_params.get("Tanim", "")))}</Tanim>'
                '</EntegrasyonParams>'
            )

        def _fdate(key):
            val = filtre.get(key)
            if not val:
                return ''
            return f'<{key}>{xml_escape(str(val))}</{key}>'

        filtre_xml = (
            '<f>'
            f'<EntegrasyonAktarildi>{int(filtre.get("EntegrasyonAktarildi", -1))}</EntegrasyonAktarildi>'
            f'{ep_xml}'
            f'<OdemeDurumu>{int(filtre.get("OdemeDurumu", -1))}</OdemeDurumu>'
            f'<OdemeTipi>{int(filtre.get("OdemeTipi", -1))}</OdemeTipi>'
            f'<SiparisDurumu>{int(filtre.get("SiparisDurumu", -1))}</SiparisDurumu>'
            f'<SiparisID>{int(filtre.get("SiparisID", 0))}</SiparisID>'
            f'{_fdate("SiparisTarihBas")}'
            f'{_fdate("SiparisTarihSon")}'
            f'<UyeID>{int(filtre.get("UyeID", 0))}</UyeID>'
            '</f>'
        )
        sayfalama_xml = (
            '<s>'
            f'<BaslangicIndex>{int(sayfalama.get("BaslangicIndex", 0))}</BaslangicIndex>'
            f'<KayitSayisi>{int(sayfalama.get("KayitSayisi", 50))}</KayitSayisi>'
            f'<SiralamaDegeri>{xml_escape(str(sayfalama.get("SiralamaDegeri", "ID")))}</SiralamaDegeri>'
            f'<SiralamaYonu>{xml_escape(str(sayfalama.get("SiralamaYonu", "DESC")))}</SiralamaYonu>'
            '</s>'
        )
        body = (
            f'<SelectSiparis xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'{filtre_xml}'
            f'{sayfalama_xml}'
            '</SelectSiparis>'
        )
        result = self._call('SiparisServis', 'ISiparisServis', 'SelectSiparis', body)
        return _ensure_list(result.get('SelectSiparisResult', {}).get('WebSiparis'))

    def select_siparis_odeme(self, siparis_id, odeme_id=0):
        body = (
            f'<SelectSiparisOdeme xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'<siparisId>{int(siparis_id)}</siparisId>'
            f'<odemeId>{int(odeme_id)}</odemeId>'
            '</SelectSiparisOdeme>'
        )
        result = self._call('SiparisServis', 'ISiparisServis', 'SelectSiparisOdeme', body)
        return _ensure_list(result.get('SelectSiparisOdemeResult', {}).get('WebSiparisOdeme'))

    def select_siparis_urun(self, siparis_id):
        body = (
            f'<SelectSiparisUrun xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'<siparisId>{int(siparis_id)}</siparisId>'
            '</SelectSiparisUrun>'
        )
        result = self._call('SiparisServis', 'ISiparisServis', 'SelectSiparisUrun', body)
        return _ensure_list(result.get('SelectSiparisUrunResult', {}).get('WebSiparisUrun'))

    def save_siparis(self, uye_id, fatura_adres_id, kargo_adres_id, kargo_firma_id,
                     urunler, odeme_durumu=1, odeme_tipi=10, siparis_kaynagi='Entegrasyon'):
        """
        urunler: list of dict — UrunID, Adet, KdvTutari, Tutar
        """
        urun_tutari = sum(float(u.get('Tutar', 0)) * int(u.get('Adet', 1)) for u in urunler)
        urun_tutari_kdv = sum(float(u.get('KdvTutari', 0)) * int(u.get('Adet', 1)) for u in urunler)

        urunler_xml = ''
        for u in urunler:
            urunler_xml += (
                '<WebSiparisSaveUrun>'
                f'<Adet>{int(u.get("Adet", 1))}</Adet>'
                f'<KdvTutari>{float(u.get("KdvTutari", 0))}</KdvTutari>'
                f'<Tutar>{float(u.get("Tutar", 0))}</Tutar>'
                f'<UrunID>{int(u.get("UrunID", 0))}</UrunID>'
                '</WebSiparisSaveUrun>'
            )

        body = (
            f'<SaveSiparis xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<req>'
            f'<UyeId>{int(uye_id)}</UyeId>'
            f'<FaturaAdresId>{int(fatura_adres_id)}</FaturaAdresId>'
            f'<KargoAdresId>{int(kargo_adres_id)}</KargoAdresId>'
            f'<KargoFirmaId>{int(kargo_firma_id)}</KargoFirmaId>'
            f'<SiparisKaynagi>{xml_escape(str(siparis_kaynagi))}</SiparisKaynagi>'
            f'<Urunler>{urunler_xml}</Urunler>'
            f'<UrunTutari>{urun_tutari}</UrunTutari>'
            f'<UrunTutariKdv>{urun_tutari_kdv}</UrunTutariKdv>'
            '<Odeme>'
            f'<OdemeDurumu>{int(odeme_durumu)}</OdemeDurumu>'
            f'<OdemeTipi>{int(odeme_tipi)}</OdemeTipi>'
            f'<Tutar>{urun_tutari + urun_tutari_kdv}</Tutar>'
            '</Odeme>'
            '</req>'
            '</SaveSiparis>'
        )
        result = self._call('SiparisServis', 'ISiparisServis', 'SaveSiparis', body)
        resp = result.get('SaveSiparisResult', {})
        is_error = resp.get('IsError', 'false')
        if str(is_error).lower() == 'true':
            raise TicimaxError(f'SaveSiparis hatası: {resp.get("ErrorMessage", "")}')
        return resp

    # ------------------------------------------------------------------
    # 3. UyeServis
    # ------------------------------------------------------------------

    def giris_yap(self, mail, sifre):
        body = (
            f'<GirisYap xmlns="{TEMPURI}">'
            '<ug>'
            f'<Mail>{xml_escape(str(mail))}</Mail>'
            f'<Sifre>{xml_escape(str(sifre))}</Sifre>'
            '</ug>'
            '</GirisYap>'
        )
        result = self._call('UyeServis', 'IUyeServis', 'GirisYap', body)
        return result.get('GirisYapResult', {})

    def select_uyeler(self, filtre=None, sayfalama=None):
        """
        filtre: dict — Aktif, AlisverisYapti, Cinsiyet, MailIzin, SmsIzin, Mail (-1/0/1)
        """
        filtre = filtre or {}
        sayfalama = sayfalama or {}

        filtre_xml = (
            '<filtre>'
            f'<Aktif>{int(filtre.get("Aktif", -1))}</Aktif>'
            f'<AlisverisYapti>{int(filtre.get("AlisverisYapti", -1))}</AlisverisYapti>'
            f'<Cinsiyet>{int(filtre.get("Cinsiyet", -1))}</Cinsiyet>'
            f'<MailIzin>{int(filtre.get("MailIzin", -1))}</MailIzin>'
            f'<SmsIzin>{int(filtre.get("SmsIzin", -1))}</SmsIzin>'
            f'<Mail>{xml_escape(str(filtre.get("Mail", "")))}</Mail>'
            '</filtre>'
        )
        sayfalama_xml = ''
        if sayfalama:
            sayfalama_xml = (
                '<sayfalama>'
                f'<BaslangicIndex>{int(sayfalama.get("BaslangicIndex", 0))}</BaslangicIndex>'
                f'<KayitSayisi>{int(sayfalama.get("KayitSayisi", 50))}</KayitSayisi>'
                '</sayfalama>'
            )
        else:
            sayfalama_xml = '<sayfalama i:nil="true" xmlns:i="http://www.w3.org/2001/XMLSchema-instance"/>'

        body = (
            f'<SelectUyeler xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            f'<uye>{filtre_xml}</uye>'
            f'{sayfalama_xml}'
            '</SelectUyeler>'
        )
        result = self._call('UyeServis', 'IUyeServis', 'SelectUyeler', body)
        return _ensure_list(result.get('SelectUyelerResult', {}).get('WebUye'))

    def save_uye(self, mail, sifre, isim, soyisim, telefon='', cep_telefonu='',
                 dogum_tarihi='', cinsiyet_id=1, mail_izin=1, sms_izin=1, uye_id=0):
        body = (
            f'<SaveUye xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<uye>'
            f'<Mail>{xml_escape(str(mail))}</Mail>'
            f'<Sifre>{xml_escape(str(sifre))}</Sifre>'
            f'<Isim>{xml_escape(str(isim))}</Isim>'
            f'<Soyisim>{xml_escape(str(soyisim))}</Soyisim>'
            f'<Telefon>{xml_escape(str(telefon))}</Telefon>'
            f'<CepTelefonu>{xml_escape(str(cep_telefonu))}</CepTelefonu>'
            f'<DogumTarihi>{xml_escape(str(dogum_tarihi))}</DogumTarihi>'
            f'<CinsiyetID>{int(cinsiyet_id)}</CinsiyetID>'
            f'<MailIzin>{int(mail_izin)}</MailIzin>'
            f'<SmsIzin>{int(sms_izin)}</SmsIzin>'
            '</uye>'
            '<ayar/>'
            '</SaveUye>'
        )
        result = self._call('UyeServis', 'IUyeServis', 'SaveUye', body)
        return result.get('SaveUyeResult', '')

    def save_uye_adres(self, uye_id, adres, alici_adi, alici_telefon, ilce, sehir,
                       ulke='Türkiye', firma_adi='', tanim='Adres', aktif=True):
        body = (
            f'<SaveUyeAdres xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<adres>'
            f'<UyeId>{int(uye_id)}</UyeId>'
            f'<Adres>{xml_escape(str(adres))}</Adres>'
            f'<Aktif>{_bool_xml(aktif)}</Aktif>'
            f'<AliciAdi>{xml_escape(str(alici_adi))}</AliciAdi>'
            f'<AliciTelefon>{xml_escape(str(alici_telefon))}</AliciTelefon>'
            f'<FirmaAdi>{xml_escape(str(firma_adi))}</FirmaAdi>'
            f'<Ilce>{xml_escape(str(ilce))}</Ilce>'
            f'<Sehir>{xml_escape(str(sehir))}</Sehir>'
            f'<Tanim>{xml_escape(str(tanim))}</Tanim>'
            f'<Ulke>{xml_escape(str(ulke))}</Ulke>'
            '</adres>'
            '</SaveUyeAdres>'
        )
        result = self._call('UyeServis', 'IUyeServis', 'SaveUyeAdres', body)
        try:
            return int(result.get('SaveUyeAdresResult', 0))
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------
    # 4. CustomServis
    # ------------------------------------------------------------------

    def save_entegrasyon_id(self, entegrasyon_kodu, tablo_alan, alan_deger, tanim, deger):
        """
        entegrasyon_kodu: 'ERP' gibi program adı
        tablo_alan: Ticimax'taki tablo/sütun adı (ör. 'TICIMAXURUNID')
        alan_deger: Ticimax'taki sütun değeri (tekil anahtar)
        tanim: program tarafındaki sütun adı (ör. 'ERPSTOKID')
        deger: program tarafındaki sütun değeri
        """
        body = (
            f'<SaveEntegrasyonId xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<entegrasyon>'
            f'<EntegrasyonKodu>{xml_escape(str(entegrasyon_kodu))}</EntegrasyonKodu>'
            f'<TabloAlan>{xml_escape(str(tablo_alan))}</TabloAlan>'
            f'<AlanDeger>{xml_escape(str(alan_deger))}</AlanDeger>'
            f'<Tanim>{xml_escape(str(tanim))}</Tanim>'
            f'<Deger>{xml_escape(str(deger))}</Deger>'
            '</entegrasyon>'
            '</SaveEntegrasyonId>'
        )
        self._call('CustomServis', 'ICustomServis', 'SaveEntegrasyonId', body)

    def select_entegrasyon_id(self, entegrasyon_kodu, tablo_alan, alan_deger, tanim):
        """Program tarafındaki ID değerini döndürür."""
        body = (
            f'<SelectEntegrasyonId xmlns="{TEMPURI}">'
            f'<UyeKodu>{xml_escape(self.uye_kodu)}</UyeKodu>'
            '<entegrasyon>'
            f'<EntegrasyonKodu>{xml_escape(str(entegrasyon_kodu))}</EntegrasyonKodu>'
            f'<TabloAlan>{xml_escape(str(tablo_alan))}</TabloAlan>'
            f'<AlanDeger>{xml_escape(str(alan_deger))}</AlanDeger>'
            f'<Tanim>{xml_escape(str(tanim))}</Tanim>'
            '</entegrasyon>'
            '</SelectEntegrasyonId>'
        )
        result = self._call('CustomServis', 'ICustomServis', 'SelectEntegrasyonId', body)
        return result.get('SelectEntegrasyonIdResult', '')
