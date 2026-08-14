# -*- coding: utf-8 -*-
from odoo.addons.iber_edonusum.models.integrator_base import IntegratorBase
import requests
from urllib.parse import urlparse

from ..core.nes_helpers import _clean_xml_for_display


class NesIntegrator(IntegratorBase):
    code = "NES"
    name = "NES e-Transformation"

    # NES documentStatus → gib_status
    status_map = {
        "APPROVED": "approved",
        "SUCCEED":  "approved",
        "SUCCESS":  "approved",
        "REJECTED": "rejected",
        "FAILED":   "rejected",
        "ERROR":    "error",
        "WAITING":  "sent",
        "SENDING":  "sent",
        "QUEUED":   "sent",
    }

    # NES documentAnswer → iç cevap değeri
    answer_map = {
        "none":     "none",
        "waiting":  "waiting",
        "accepted": "accepted",
        "rejected": "rejected",
    }

    def _base_url(self):
        """
        edn.integrator.base_url'den sadece scheme+host kısmını döner.
        Örn: "https://apitest.nes.com.tr/einvoice/v1/" → "https://apitest.nes.com.tr"
        """
        raw = self.settings.get("url", "").strip().rstrip("/")
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return raw  # parse edilemeyen URL'i olduğu gibi kullan

    def _headers(self, token=None):
        """
        token verilmezse settings'ten api_token veya apikey alır.
        """
        resolved_token = token or self.settings.get("api_token") or self.settings.get("apikey") or ""
        if not resolved_token:
            raise ValueError(
                "NES token not found. Fill in the API Key or "
                "api_token value in the integrator settings."
            )
        return {
            "Authorization": f"Bearer {resolved_token}",
        }
    
    def get_token(self) -> dict:
        # NES örneğinde APIKEY doğrulama userinfo ile yapılabiliyordu
        url = f"{self._base_url()}/connect/userinfo"
        try:
            resp = requests.get(url, headers=self._headers(with_token=False), timeout=30)
            raw = resp.json() if resp.content else {}
            ok = resp.ok and bool(raw)
            token = self.settings.get("apikey") if ok else None  # userinfo ile APIKEY doğrulaması
            return {"ok": ok, "token": token, "raw": raw, "error": None if ok else f"HTTP {resp.status_code} {raw}"}
        except Exception as ex:
            return {"ok": False, "token": None, "raw": None, "error": str(ex)}

    def send_document(self, document):
        """
        C# fonksiyonunun Python karşılığıdır.
        /einvoice/v1/uploads/document veya /earchive/v1/uploads/document
        endpointine multipart/form-data gönderir.
        """
        
        isEArchive = True if document.get("DocumentProfile") == "EARSIVFATURA" else False
        try:
            base_url = self._base_url()
            if isEArchive:
                endpoint = "/earchive/v1/uploads/document"
            else:
                endpoint = "/einvoice/v1/uploads/document"
            if document.get("DocumentType") == "DespatchAdvice":
                endpoint = "/edespatch/v1/uploads/document"

            url = f"{base_url}{endpoint}"

            # Dosya ve parametreler
            files = {
                "File": (f"{document['UUID']}.xml",
                         document["File"].encode("utf-8"),
                         "text/xml")
            }
            data = {
                "IsDirectSend": str(document.get("IsDirectSend", True)).lower(),
                "PreviewType": document.get("PreviewType", "None"),
                "SenderAlias": document.get("SenderAlias", ""),
                "SourceApp": document.get("SourceApp", "Odoo"),
                "ReceiverAlias": document.get("ReceiverAlias", ""),
                "DocumentTemplate": document.get("DocumentTemplate", ""),
                "SourceAppRecordId": document.get("SourceAppRecordId", ""),
            }

            # Token: önce IntegratorInfo’dan, bulamazsa edn.integrator kaydındaki apikey’den al
            integrator_info = document.get("IntegratorInfo") or {}
            token = (
                integrator_info.get("api_token")
                or integrator_info.get("apikey")
                or self.settings.get("apikey")
                or self.settings.get("token")
                or ""
            )
            headers = self._headers(token)

            resp = requests.post(
                url,
                headers=headers,
                data=data,
                files=files,
                timeout=90
            )

            try:
                raw = resp.json()
            except Exception:
                raw = {"text": resp.text}

            # NES HTTP 200 dönse de body'de errors olabilir — gerçek başarıyı kontrol et
            business_errors = raw.get("errors") if isinstance(raw, dict) else None
            business_ok = resp.ok and not business_errors

            error_msg = None
            if not resp.ok:
                error_msg = f"HTTP {resp.status_code}: {resp.text}"
            elif business_errors:
                # errors listesindeki tüm description'ları birleştir
                descriptions = [
                    e.get("description", "") or e.get("detail", "") or str(e)
                    for e in business_errors
                    if isinstance(e, dict)
                ]
                error_msg = raw.get("message", "Integrator error") + ":\n" + "\n".join(descriptions)

            return {
                "ok": business_ok,
                "status_code": resp.status_code,
                "raw": raw,
                "error": error_msg
            }

        except Exception as ex:
            return {"ok": False, "raw": None, "error": str(ex)}

    def get_incoming_documents(self, filters: dict | None = None) -> dict:
        """
        Gelen e-Fatura veya e-İrsaliye belgelerini getirir.

        Args:
            filters (dict): Filtreleme parametreleri
                - document_type (str): 'invoice' veya 'despatch' (zorunlu)
                - tags (list): UUID listesi
                - userNote (str): Kullanıcı notu
                - documentNote (str): Belge notu
                - company (str): Firma ünvanı veya VKN/TCKN
                - uuid (str): Belge UUID
                - documentNumber (str): Belge numarası
                - receiverAlias (str): e-Dönüşüm etiketi
                - startCreateDate (str): Başlangıç tarihi (ISO 8601)
                - endCreateDate (str): Bitiş tarihi (ISO 8601)
                - erpTransferred (bool): ERP transfer durumu
                - isRead (bool): Okunma durumu
                - archived (bool): Arşivlenen belgeler
                - sort (str): Sıralama (örn: "CreatedAt desc")
                - pageSize (int): Sayfa başına kayıt sayısı
                - pageNumber (int): Sayfa numarası
                - include_lines (bool): Kalem bilgilerini de çek (default: True)

                Fatura için ek parametreler:
                - despatchNumber (str): İrsaliye numarası
                - orderNumber (str): Sipariş numarası
                - profileId (str): Fatura profili
                - invoiceTypeCode (str): Fatura tipi
                - documentAnswer (str): Cevap durumu

                İrsaliye için ek parametreler:
                - orderNumber (str): Sipariş numarası
                - despatchAnswer (str): İrsaliye yanıt durumu
                - despatchAdviceTypeCode (str): İrsaliye tipi

        Returns:
            dict: {"ok": bool, "raw": dict, "error": str|None}
        """
        filters = filters or {}
        document_type = filters.pop("document_type", "invoice")
        include_lines = filters.pop("include_lines", True)

            # Endpoint belirleme
        base_url = self._base_url()
        if document_type == "despatch":
            endpoint = "/edespatch/v1/incoming/despatches"
        else:
            endpoint = "/einvoice/v1/incoming/invoices"

        url = f"{base_url}{endpoint}"

        import logging as _logging
        _debug = _logging.getLogger("nes_integrator.incoming")

        try:
                # Tarih aralığını kontrol et ve 30 günlük parçalara böl
            from datetime import datetime, timedelta

            start_date = filters.get('startCreateDate') or filters.get('startDate')
            end_date = filters.get('endCreateDate') or filters.get('endDate')
            if start_date and not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
                # Tüm sonuçları birleştireceğimiz liste
            all_items = []

            # ----------------------------------------------------------------------
            #  🔹 SAYFALAMA İÇİN GENEL FONKSİYON
            # ----------------------------------------------------------------------
            def fetch_with_paging(base_filters):
                """Servis 100'lük limitte döndüğünde tüm sayfaları alır."""
                page = 1
                page_size = 100
                collected = []

                while True:
                    paged_filters = base_filters.copy()
                    paged_filters["pageNumber"] = page
                    paged_filters["pageSize"] = page_size

                    resp = requests.get(url, headers=self._headers(), params=paged_filters, timeout=60)
                    raw_page = resp.json() if resp.content else {}

                    if not resp.ok:
                        return {"ok": False, "error": f"HTTP {resp.status_code} {raw_page}", "items": []}

                    data = raw_page.get("data", [])

                    collected.extend(data)

                    # Gelen veri 100 adetten az ise sayfa bitti demektir
                    if len(data) < page_size:
                        break

                    page += 1

                return {"ok": True, "error": None, "items": collected}

            # ----------------------------------------------------------------------
            #  🔹 30 GÜNLÜK BÖLÜNEN TARİH ALANLARI VARSA
            # ----------------------------------------------------------------------
            if start_date and end_date:
                    # Tarih string'lerini datetime'a çevir
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                except:
                        # ISO format değilse, standart format dene
                    start_dt = datetime.strptime(start_date[:10], '%Y-%m-%d')
                    end_dt = datetime.strptime(end_date[:10], '%Y-%m-%d')

                    # Tarih farkını hesapla
                date_diff = (end_dt - start_dt).days

                if date_diff > 30:
                        # 30 günlük parçalara böl
                    current_start = start_dt

                    while current_start < end_dt:
                            # 30 gün ekle, ama end_date'i geçme
                        current_end = min(current_start + timedelta(days=30), end_dt)

                            # Bu aralık için filters kopyası oluştur
                        chunk_filters = filters.copy()

                            # Tarih filtrelerini güncelle
                        if 'startCreateDate' in filters or 'endCreateDate' in filters:
                            chunk_filters['startCreateDate'] = current_start.strftime('%Y-%m-%d')
                            chunk_filters['endCreateDate'] = current_end.strftime('%Y-%m-%d')
                        else:
                            chunk_filters['startDate'] = current_start.strftime('%Y-%m-%d')
                            chunk_filters['endDate'] = current_end.strftime('%Y-%m-%d')

                        result = fetch_with_paging(chunk_filters)
                        if not result["ok"]:
                            return {"ok": False, "raw": result, "error": result["error"]}

                        all_items.extend(result["items"])

                        current_start = current_end + timedelta(days=1)

                    raw = {"data": all_items, "totalCount": len(all_items)}
                else:
                    result = fetch_with_paging(filters)
                    if not result["ok"]:
                        return {"ok": False, "raw": result, "error": result["error"]}

                    raw = {"data": result["items"], "totalCount": len(result["items"])}

            else:
                # ------------------------------------------------------------------
                #  🔹 TARİH FİLTRESİ YOK → NORMALDE TEK SAYFA ÇAĞRI YAPARDI
                #     ARTIK TÜM SAYFALAR OTOMATİK ALINIYOR
                # ------------------------------------------------------------------
                result = fetch_with_paging(filters)
                if not result["ok"]:
                    return {"ok": False, "raw": result, "error": result["error"]}

                raw = {"data": result["items"], "totalCount": len(result["items"])}

            # ----------------------------------------------------------------------
            #  🔹 LINES ÇEKME (AYNI SENİN MEVCUT KODUN)
            # ----------------------------------------------------------------------
            if include_lines and isinstance(raw, dict) and 'data' in raw:
                items = raw.get('data', [])
                for item in items:
                    uuid = item.get('id') or item.get('uuid')
                    if not uuid:
                        item['lines'] = []
                        continue

                    try:
                                # Kalem bilgilerini çek
                        if document_type == "despatch":
                            lines_result = self.get_despatch_lines(uuid)
                        else:
                            lines_result = self.get_invoice_lines(uuid)

                        if lines_result.get('ok'):
                            lines_raw = lines_result.get('raw', {})
                            if isinstance(lines_raw, dict):
                                item['lines'] = lines_raw.get('data', [])

                                # XML başlık verisini item'a ekle (gönderici/alıcı/adres)
                                xml_header = lines_raw.get('header', {})
                                if xml_header:
                                    item['_xml_header'] = xml_header
                                # Temizlenmiş XML (namespace'siz)
                                xml_clean = lines_raw.get('xml_clean')
                                if xml_clean:
                                    item['_xml_data'] = xml_clean

                                if document_type == "invoice":
                                    # Belge toplamlarını güncelle
                                    totals = lines_raw.get('documentTotals', {})
                                    if totals:
                                        item['lineExtensionAmount'] = float(totals.get('lineExtensionAmount') or 0)
                                        item['taxAmount']           = float(totals.get('taxAmount') or 0)
                                        item['payableAmount']       = float(totals.get('payableAmount') or 0)
                                        if totals.get('currencyID'):
                                            item['documentCurrencyCode'] = totals['currencyID']
                            else:
                                item['lines'] = []

                    except Exception:
                        item['lines'] = []

            return {"ok": True, "raw": raw, "error": None}

        except Exception as ex:
            return {"ok": False, "raw": None, "error": str(ex)}

    def check_document_status(self, uuid: str) -> dict:
        url = f"{self._base_url()}/api/efatura/status/{uuid}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            raw = resp.json() if resp.content else {}
            return {"ok": resp.ok, "raw": raw, "error": None if resp.ok else f"HTTP {resp.status_code} {raw}"}
        except Exception as ex:
            return {"ok": False, "raw": None, "error": str(ex)}

    def get_despatch_lines(self, uuid: str) -> dict:
        """
        Gelen irsaliye kalemlerini UBL XML'den parse ederek getirir.

        Args:
            uuid (str): İrsaliye UUID

        Returns:
            dict: {"ok": bool, "raw": dict/list, "error": str|None}
        """
        base_url = self._base_url()
        url = f"{base_url}/edespatch/v1/incoming/despatches/{uuid}/xml"

        try:
            resp = requests.get(url, headers=self._headers(), timeout=60)

            if not resp.ok:
                return {"ok": False, "raw": None, "error": f"HTTP {resp.status_code}"}

            # UBL XML'i parse et
            try:
                import xml.etree.ElementTree as ET

                # XML namespace'leri
                namespaces = {
                    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
                    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
                    'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2'
                }

                root = ET.fromstring(resp.content)
                ns = namespaces

                # Başlık bilgileri
                def _t(node, path):
                    el = node.find(path, ns) if node is not None else None
                    return el.text.strip() if el is not None and el.text else None

                despatch_id = _t(root, 'cbc:ID')
                issue_date  = _t(root, 'cbc:IssueDate')

                supplier_party = root.find('.//cac:DespatchSupplierParty/cac:Party', ns)
                customer_party = root.find('.//cac:DeliveryCustomerParty/cac:Party', ns)

                def _parse_party_despatch(party_node):
                    if party_node is None:
                        return {}
                    return {
                        "taxNumber": _t(party_node, 'cac:PartyIdentification/cbc:ID'),
                        "name": _t(party_node, 'cac:PartyName/cbc:Name'),
                        "taxOfficeName": _t(party_node, 'cac:PartyTaxScheme/cbc:TaxLevelCode'),
                        "streetName": _t(party_node, 'cac:PostalAddress/cbc:StreetName'),
                        "cityName": _t(party_node, 'cac:PostalAddress/cbc:CityName'),
                        "citySubdivision": _t(party_node, 'cac:PostalAddress/cbc:CitySubdivisionName'),
                        "postalZone": _t(party_node, 'cac:PostalAddress/cbc:PostalZone'),
                        "countryCode": _t(party_node, 'cac:PostalAddress/cac:Country/cbc:IdentificationCode'),
                    }

                header = {
                    "id": despatch_id,
                    "issueDate": issue_date,
                    "supplier": _parse_party_despatch(supplier_party),
                    "customer": _parse_party_despatch(customer_party),
                }

                # DespatchLine elementlerini bul
                lines = []
                for line in root.findall('.//cac:DespatchLine', namespaces):
                    item_data = {}

                    # ID (sıra no)
                    id_elem = line.find('cbc:ID', namespaces)
                    if id_elem is not None:
                        item_data['id'] = id_elem.text

                    # Miktar
                    qty_elem = line.find('.//cbc:DeliveredQuantity', namespaces)
                    if qty_elem is not None:
                        item_data['quantity'] = qty_elem.text
                        item_data['unitCode'] = qty_elem.get('unitCode', '')

                    # Item bilgileri
                    item_elem = line.find('cac:Item', namespaces)
                    if item_elem is not None:
                        # Ürün adı
                        name_elem = item_elem.find('cbc:Name', namespaces)
                        if name_elem is not None:
                            item_data['name'] = name_elem.text

                        # Açıklama/Not
                        desc_elem = item_elem.find('cbc:Description', namespaces)
                        if desc_elem is not None:
                            item_data['note'] = desc_elem.text

                        # Satıcı ürün kodu
                        sellers_id = item_elem.find('.//cac:SellersItemIdentification/cbc:ID', namespaces)
                        if sellers_id is not None:
                            item_data['sellersItemIdentification'] = sellers_id.text

                        # GTIP
                        commodity_elem = item_elem.find('.//cac:CommodityClassification/cbc:ItemClassificationCode', namespaces)
                        if commodity_elem is not None:
                            item_data['commodityClassificationId'] = commodity_elem.text

                    # Fiyat bilgileri (varsa)
                    shipment = line.find('cac:Shipment', namespaces)
                    if shipment is not None:
                        goods_item = shipment.find('cac:GoodsItem', namespaces)
                        if goods_item is not None:
                            # Değer
                            value_elem = goods_item.find('cbc:DeclaredCustomsValueAmount', namespaces)
                            if value_elem is not None:
                                item_data['lineExtensionAmount'] = value_elem.text
                                item_data['currencyId'] = value_elem.get('currencyID', 'TRY')

                    lines.append(item_data)

                return {
                    "ok": True,
                    "raw": {
                        "data": lines,
                        "header": header,
                        "xml_clean": _clean_xml_for_display(resp.content),
                    },
                    "error": None,
                }

            except ET.ParseError as e:
                return {"ok": False, "raw": None, "error": f"XML parse error: {str(e)}"}

        except Exception as ex:
            return {"ok": False, "raw": None, "error": str(ex)}

    def get_invoice_lines(self, uuid: str) -> dict:
        """
        Gelen fatura UBL XML'ini parse eder.
        Başlık bilgileri (gönderici, alıcı, adres, tarihler, tutarlar) +
        kalem listesi döndürür.

        Returns:
            dict: {"ok": bool, "raw": {"data": [...], "header": {...}, "documentTotals": {...}}, "error": str|None}
        """
        import xml.etree.ElementTree as ET

        NS = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        }

        def _t(node, path):
            """Verilen path'teki ilk elemanın text değeri, yoksa None."""
            if node is None:
                return None
            el = node.find(path, NS)
            return el.text.strip() if el is not None and el.text else None

        def _attr(node, path, attr):
            if node is None:
                return None
            el = node.find(path, NS)
            return el.get(attr) if el is not None else None

        def _parse_party(party_node):
            """cac:AccountingSupplierParty / AccountingCustomerParty'yi dict'e çevirir."""
            if party_node is None:
                return {}
            party = party_node.find('cac:Party', NS) or party_node
            result = {}
            # VKN/TCKN
            for pid in party.findall('cac:PartyIdentification', NS):
                id_el = pid.find('cbc:ID', NS)
                if id_el is not None and id_el.text:
                    scheme = id_el.get('schemeID', 'VKN')
                    result['taxNumber'] = id_el.text.strip()
                    result['taxScheme'] = scheme
            # Unvan
            pname = party.find('cac:PartyName/cbc:Name', NS)
            if pname is not None and pname.text:
                result['name'] = pname.text.strip()
            # Vergi dairesi
            tax_scheme = party.find('cac:PartyTaxScheme/cac:TaxScheme/cbc:Name', NS)
            if tax_scheme is not None and tax_scheme.text:
                result['taxOfficeName'] = tax_scheme.text.strip()
            # Adres
            addr = party.find('cac:PostalAddress', NS)
            if addr is not None:
                result['streetName']       = _t(addr, 'cbc:StreetName') or ''
                result['buildingNumber']   = _t(addr, 'cbc:BuildingNumber') or ''
                result['citySubdivision']  = _t(addr, 'cbc:CitySubdivisionName') or ''
                result['cityName']         = _t(addr, 'cbc:CityName') or ''
                result['postalZone']       = _t(addr, 'cbc:PostalZone') or ''
                result['district']         = _t(addr, 'cbc:CountrySubentity') or \
                                             _t(addr, 'cbc:District') or ''
                country_el = addr.find('cac:Country/cbc:IdentificationCode', NS)
                result['countryCode']      = country_el.text.strip() if country_el is not None and country_el.text else 'TR'
            # Kişi adı (gerçek kişi faturaları)
            person = party.find('cac:Person', NS)
            if person is not None:
                first = _t(person, 'cbc:FirstName') or ''
                last  = _t(person, 'cbc:FamilyName') or ''
                if first or last:
                    result['personName'] = f"{first} {last}".strip()
            return result

        base_url = self._base_url()
        url = f"{base_url}/einvoice/v1/incoming/invoices/{uuid}/xml"

        try:
            resp = requests.get(url, headers=self._headers(), timeout=60)
            if not resp.ok:
                return {"ok": False, "raw": None, "error": f"HTTP {resp.status_code}"}

            try:
                root = ET.fromstring(resp.content)

                # ------------------------------------------------------------------
                # BAŞLIK BİLGİLERİ
                # ------------------------------------------------------------------
                header = {}
                header['uuid']            = _t(root, 'cbc:UUID') or uuid
                header['id']              = _t(root, 'cbc:ID')
                header['issueDate']       = _t(root, 'cbc:IssueDate')
                header['issueTime']       = _t(root, 'cbc:IssueTime')
                header['invoiceTypeCode'] = _t(root, 'cbc:InvoiceTypeCode')
                header['profileId']       = _t(root, 'cbc:ProfileID') or _t(root, 'cbc:CustomizationID')
                header['currencyCode']    = _t(root, 'cbc:DocumentCurrencyCode') or 'TRY'
                header['note']            = _t(root, 'cbc:Note')

                # Gönderici & Alıcı
                header['supplier'] = _parse_party(root.find('cac:AccountingSupplierParty', NS))
                header['customer'] = _parse_party(root.find('cac:AccountingCustomerParty', NS))

                # Ödeme koşulları
                header['paymentMeans']    = _t(root, 'cac:PaymentMeans/cbc:PaymentMeansCode')
                header['paymentDueDate']  = _t(root, 'cac:PaymentTerms/cbc:PaymentDueDate') or \
                                            _t(root, 'cac:PaymentMeans/cbc:PaymentDueDate')

                # ------------------------------------------------------------------
                # BELGE TOPLAMLARI
                # ------------------------------------------------------------------
                document_totals = {}
                legal_total = root.find('cac:LegalMonetaryTotal', NS)
                if legal_total is not None:
                    for field, path in [
                        ('lineExtensionAmount', 'cbc:LineExtensionAmount'),
                        ('taxExclusiveAmount',  'cbc:TaxExclusiveAmount'),
                        ('taxInclusiveAmount',  'cbc:TaxInclusiveAmount'),
                        ('payableAmount',       'cbc:PayableAmount'),
                    ]:
                        el = legal_total.find(path, NS)
                        if el is not None and el.text:
                            document_totals[field] = el.text
                            if field == 'lineExtensionAmount':
                                document_totals['currencyID'] = el.get('currencyID', 'TRY')

                tax_total_elem = root.find('cac:TaxTotal', NS)
                if tax_total_elem is not None:
                    tax_el = tax_total_elem.find('cbc:TaxAmount', NS)
                    if tax_el is not None and tax_el.text:
                        document_totals['taxAmount'] = tax_el.text

                # ------------------------------------------------------------------
                # FATURA KALEMLERİ
                # ------------------------------------------------------------------
                lines = []
                for line in root.findall('.//cac:InvoiceLine', NS):
                    item_data = {}
                    item_data['id']       = _t(line, 'cbc:ID')
                    qty_el = line.find('cbc:InvoicedQuantity', NS)
                    if qty_el is not None:
                        item_data['quantity'] = qty_el.text
                        item_data['unitCode'] = qty_el.get('unitCode', '')

                    amt_el = line.find('cbc:LineExtensionAmount', NS)
                    if amt_el is not None:
                        item_data['lineExtensionAmount'] = amt_el.text
                        item_data['currencyID'] = amt_el.get('currencyID', 'TRY')

                    item_el = line.find('cac:Item', NS)
                    if item_el is not None:
                        item_data['name']        = _t(item_el, 'cbc:Name') or ''
                        item_data['description'] = _t(item_el, 'cbc:Description') or ''
                        sellers_id = item_el.find('.//cac:SellersItemIdentification/cbc:ID', NS)
                        if sellers_id is not None and sellers_id.text:
                            item_data['sellersItemIdentification'] = sellers_id.text

                    price_el = line.find('.//cac:Price/cbc:PriceAmount', NS)
                    if price_el is not None:
                        item_data['priceAmount'] = price_el.text

                    # Tüm TaxTotal/TaxSubtotal'ları gez: KDV (0015) ana alanlara,
                    # diğerleri (ÖTV, Stopaj vb.) taxExtras listesine yazılır.
                    tax_extras = []
                    for tax_total in line.findall('cac:TaxTotal', NS):
                        for tax_sub in tax_total.findall('cac:TaxSubtotal', NS):
                            tax_scheme = tax_sub.find('cac:TaxCategory/cac:TaxScheme', NS)
                            scheme_code = (_t(tax_scheme, 'cbc:TaxTypeCode') if tax_scheme is not None else '') or \
                                          (_t(tax_scheme, 'cbc:ID') if tax_scheme is not None else '') or '0015'
                            scheme_name = (_t(tax_scheme, 'cbc:Name') if tax_scheme is not None else '') or ''
                            taxable_amount = _t(tax_sub, 'cbc:TaxableAmount') or '0'
                            tax_amount = _t(tax_sub, 'cbc:TaxAmount') or '0'
                            percent = _t(tax_sub, 'cbc:Percent') or \
                                      _t(tax_sub, 'cac:TaxCategory/cbc:Percent') or '0'

                            if scheme_code == '0015':
                                item_data['taxableAmount'] = taxable_amount
                                item_data['taxAmount'] = tax_amount
                                item_data['percent'] = percent
                            else:
                                tax_extras.append({
                                    'code': scheme_code,
                                    'name': scheme_name,
                                    'rate': percent,
                                    'taxableAmount': taxable_amount,
                                    'amount': tax_amount,
                                })
                    if tax_extras:
                        item_data['taxExtras'] = tax_extras

                    # Tevkifat (cac:WithholdingTaxTotal)
                    wh_total = line.find('cac:WithholdingTaxTotal', NS)
                    if wh_total is not None:
                        wh_sub = wh_total.find('cac:TaxSubtotal', NS)
                        if wh_sub is not None:
                            wh_scheme = wh_sub.find('cac:TaxCategory/cac:TaxScheme', NS)
                            wh_code = (_t(wh_scheme, 'cbc:TaxTypeCode') if wh_scheme is not None else '') or \
                                      (_t(wh_scheme, 'cbc:ID') if wh_scheme is not None else '') or ''
                            item_data['withholdingRate'] = _t(wh_sub, 'cbc:Percent') or '0'
                            item_data['withholdingCode'] = wh_code

                    try:
                        item_data['payableAmount'] = str(
                            float(item_data.get('lineExtensionAmount') or 0) +
                            float(item_data.get('taxAmount') or 0)
                        )
                    except (ValueError, TypeError):
                        item_data['payableAmount'] = item_data.get('lineExtensionAmount', '0')

                    # Satır iskonto/arttırım (cac:AllowanceCharge)
                    discounts = []
                    for ac in line.findall('cac:AllowanceCharge', NS):
                        charge_indicator = (_t(ac, 'cbc:ChargeIndicator') or 'false').strip().lower() == 'true'
                        discounts.append({
                            'type': 'surcharge' if charge_indicator else 'discount',
                            'rate': _t(ac, 'cbc:MultiplierFactorNumeric') or '0',
                            'amount': _t(ac, 'cbc:Amount') or '0',
                            'baseAmount': _t(ac, 'cbc:BaseAmount') or '0',
                            'description': _t(ac, 'cbc:AllowanceChargeReason') or '',
                        })
                    if discounts:
                        item_data['discounts'] = discounts

                    lines.append(item_data)

                return {
                    "ok": True,
                    "raw": {
                        "data": lines,
                        "header": header,
                        "documentTotals": document_totals,
                        "xml_bytes": resp.content,
                        "xml_clean": _clean_xml_for_display(resp.content),
                    },
                    "error": None,
                }

            except ET.ParseError as e:
                return {"ok": False, "raw": None, "error": f"XML parse error: {str(e)}"}

        except Exception as ex:
            return {"ok": False, "raw": None, "error": str(ex)}

    def get_series(self, document_type: str = "invoice") -> dict:
        """
        Entegratörden kayıtlı fatura/irsaliye serilerini çeker.

        Args:
            document_type: 'invoice' | 'despatch' | 'earchive'

        Returns:
            {"ok": bool, "raw": list, "error": str|None}
        """
        base_url = self._base_url()

        if document_type == "despatch":
            endpoint = "/edespatch/v1/definitions/series"
        elif document_type == "earchive":
            endpoint = "/earchive/v1/definitions/series"
        else:
            endpoint = "/einvoice/v1/definitions/series"

        url = f"{base_url}{endpoint}"

        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)

            try:
                raw = resp.json()
            except Exception:
                raw = {"text": resp.text}

            if not resp.ok:
                return {
                    "ok": False,
                    "raw": None,
                    "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                }

            # NES yanıtı list veya {"data": [...]} olabilir
            series_list = raw if isinstance(raw, list) else raw.get("data", raw)

            return {"ok": True, "raw": series_list, "error": None}

        except Exception as ex:
            return {"ok": False, "raw": None, "error": str(ex)}

    def get_outgoing_invoice(self, uuid: str) -> dict:
        """
        Giden e-faturanın son durumunu ve bilgilerini çeker.
        GET /einvoice/v1/outgoing/invoices/{uuid}

        Returns:
            {
                "ok": bool,
                "raw": dict,   # NES yanıtı
                "error": str|None,
                # Normalize edilmiş alanlar:
                "status": str,        # WAITING, APPROVED, REJECTED, vb.
                "envelope_id": str,   # Zarf numarası
                "invoice_number": str,# Fatura seri numarası
                "receiver_alias": str,
                "send_date": str,
                "response_date": str,
                "response_note": str,
            }
        """
        base_url = self._base_url()
        url = f"{base_url}/einvoice/v1/outgoing/invoices/{uuid}"

        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)

            try:
                raw = resp.json()
            except Exception:
                raw = {"text": resp.text}

            if not resp.ok:
                return {
                    "ok": False, "raw": raw,
                    "error": f"HTTP {resp.status_code} — URL: {url}\n{resp.text[:300]}",
                }

            # NES yanıtını normalize et (alan adları versiyona göre değişebilir)
            data = raw if isinstance(raw, dict) else {}
            return {
                "ok": True,
                "raw": raw,
                "error": None,
                "status": (
                    data.get("status") or data.get("documentStatus") or
                    data.get("invoiceStatus") or ""
                ),
                "envelope_id": (
                    data.get("envelopeId") or data.get("envelopeNumber") or
                    data.get("envelopeID") or ""
                ),
                "invoice_number": (
                    data.get("invoiceNumber") or data.get("documentNumber") or
                    data.get("id") or ""
                ),
                "receiver_alias": (
                    data.get("receiverAlias") or data.get("receiverLabel") or ""
                ),
                "send_date": (
                    data.get("sendDate") or data.get("createDate") or
                    data.get("createdAt") or ""
                ),
                "response_date": (
                    data.get("responseDate") or data.get("answerDate") or ""
                ),
                "response_note": (
                    data.get("responseNote") or data.get("answerNote") or
                    data.get("note") or ""
                ),
            }

        except Exception as ex:
            return {"ok": False, "raw": None, "error": str(ex)}

    # NES'te doc_type → endpoint path eşlemesi
    _PDF_INCOMING_PATHS = {
        "invoice":  "/einvoice/v1/incoming/invoices/{uuid}/pdf",
        "earchive": "/earchive/v1/incoming/invoices/{uuid}/pdf",
        "despatch": "/edespatch/v1/incoming/despatches/{uuid}/pdf",
    }
    _PDF_OUTGOING_PATHS = {
        "invoice":  "/einvoice/v1/outgoing/invoices/{uuid}/pdf",
        "earchive": "/earchive/v1/outgoing/invoices/{uuid}/pdf",
        "despatch": "/edespatch/v1/outgoing/despatches/{uuid}/pdf",
    }

    def get_incoming_document_pdf(self, uuid: str, doc_type: str = "invoice") -> dict:
        """Gelen belge PDF'ini NES'ten indirir. doc_type: invoice|earchive|despatch"""
        path_tpl = self._PDF_INCOMING_PATHS.get(doc_type, self._PDF_INCOMING_PATHS["invoice"])
        url = self._base_url() + path_tpl.format(uuid=uuid)
        try:
            resp = requests.get(url, headers=self._headers(), timeout=60)
            if resp.ok and resp.content:
                return {"ok": True, "pdf_bytes": resp.content, "error": None}
            return {"ok": False, "pdf_bytes": None, "error": f"HTTP {resp.status_code}"}
        except Exception as ex:
            return {"ok": False, "pdf_bytes": None, "error": str(ex)}

    def get_outgoing_document_pdf(self, uuid: str, doc_type: str = "invoice") -> dict:
        """Giden belge PDF'ini NES'ten indirir. doc_type: invoice|earchive|despatch"""
        path_tpl = self._PDF_OUTGOING_PATHS.get(doc_type, self._PDF_OUTGOING_PATHS["invoice"])
        url = self._base_url() + path_tpl.format(uuid=uuid)
        try:
            resp = requests.get(url, headers=self._headers(), timeout=60)
            if resp.ok and resp.content:
                return {"ok": True, "pdf_bytes": resp.content, "error": None}
            return {"ok": False, "pdf_bytes": None, "error": f"HTTP {resp.status_code}"}
        except Exception as ex:
            return {"ok": False, "pdf_bytes": None, "error": str(ex)}

    # Geriye dönük uyumluluk aliasları (eski çağrılar hata vermez)
    def get_incoming_invoice_pdf(self, uuid: str) -> dict:
        return self.get_incoming_document_pdf(uuid, doc_type="invoice")

    def get_outgoing_invoice_pdf(self, uuid: str) -> dict:
        return self.get_outgoing_document_pdf(uuid, doc_type="invoice")
