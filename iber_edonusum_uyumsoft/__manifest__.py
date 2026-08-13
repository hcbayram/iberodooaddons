{
    "name": "İberoDoo Uyumsoft e-Dönüşüm Entegratörü",
    "summary": "Uyumsoft e-Fatura/e-Arşiv entegrasyonu — iber_edonusum çerçevesi için Uyumsoft provider",
    "version": "19.0.1.2.0",
    "author": "İberoDoo",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "external_dependencies": {
        "python": ["requests"],
    },
    "depends": ["iber_edonusum"],
    "data": [
        "views/ubl_invoice_status_views.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}
