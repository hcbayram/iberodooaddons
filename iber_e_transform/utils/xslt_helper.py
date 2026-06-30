from saxonche import PySaxonProcessor

def xslt2_transform(xml_string, xslt_path):
    """
    XSLT 2.0 transform → HTML string döndürür.
    xml_string: XML içerik (string)
    xslt_path: XSLT dosyası yolu
    """

    with PySaxonProcessor(license=False) as proc:
        xslt = proc.new_xslt30_processor()

        # XSLT derle
        executable = xslt.compile_stylesheet(stylesheet_file=xslt_path)

        # XML string'i XdmNode olarak yükle
        xdm_doc = proc.parse_xml(xml_text=xml_string)

        # Transform çalıştır
        result = executable.transform_to_string(xdm_node=xdm_doc)

        return result
