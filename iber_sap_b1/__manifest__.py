{
    "name": "İberoDoo SAP Business One Entegrasyonu",
    "version": "19.0.1.0.0",
    "summary": "SAP Business One → iber_e_transform köprüsü: fatura ve irsaliye senkronizasyonu",
    "category": "Accounting",
    "author": "İberoDoo",
    "license": "LGPL-3",
    "depends": [
        "iber_e_transform",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "views/settings_sap_b1_views.xml",
        "views/sap_b1_list_actions.xml",
    ],
    "installable": True,
    "application": False,
}
