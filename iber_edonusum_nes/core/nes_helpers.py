# -*- coding: utf-8 -*-
"""
NES — saf Python XML görüntüleme yardımcıları (Odoo bağımsız).

models/nes_integrator.py'nin API istemci katmanından ayrıştırılmıştır
(bkz. sapb1_control_center/core paterni, Cython ile derlenebilir).
"""
import re
import xml.dom.minidom


def _clean_xml_for_display(xml_bytes: bytes) -> str:
    """
    UBL XML'i görüntüleme için temizler ve formatlar:
      - Dijital imza bloğunu (<ext:UBLExtensions>) kaldırır (base64 sertifika = 200KB+)
      - Düzgün girintili (pretty-print) XML oluşturur
      - xmlns namespace tanımlarını kaldırır (tag prefix'leri kalır: cbc:, cac: vb.)
    xml_data alanında gösterim için kullanılır; PDF render'ı etkilemez.
    """
    try:
        # 1) minidom ile parse et (namespace'leri bilir, prefix'leri korur)
        dom = xml.dom.minidom.parseString(xml_bytes)

        # 2) UBLExtensions bloğunu kaldır (dijital imza = yüzlerce KB base64)
        for node in list(dom.getElementsByTagNameNS('*', 'UBLExtensions')):
            node.parentNode.removeChild(node)

        # 3) Pretty-print (2 boşluk girinti)
        pretty = dom.toprettyxml(indent='  ', encoding=None)

        # 4) toprettyxml'in eklediği boş satırları temizle
        lines = [ln for ln in pretty.splitlines() if ln.strip()]
        pretty = '\n'.join(lines)

        # 5) xmlns namespace tanımlarını kaldır (sadece görüntüleme, veri kaybolmuyor)
        cleaned = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', pretty)
        cleaned = re.sub(r"\s+xmlns(?::\w+)?='[^']*'", '', cleaned)
        cleaned = re.sub(r'\s+xsi:schemaLocation="[^"]*"', '', cleaned)

        return cleaned
    except Exception:
        # Fallback: ham text, en azından xmlns temizlensin
        try:
            text = xml_bytes.decode("utf-8")
            text = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', text)
            text = re.sub(r'\s+xsi:schemaLocation="[^"]*"', '', text)
            return text
        except Exception:
            return xml_bytes.decode("utf-8", errors="replace")
