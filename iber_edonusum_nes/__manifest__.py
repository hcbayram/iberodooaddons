{
    "name": "İberoDoo NES e-Dönüşüm Entegratörü",
    "summary": "NES e-Dönüşüm API entegrasyonu — iber_edonusum çerçevesi için NES provider",
    "version": "19.0.1.3.0",
    "author": "İberoDoo",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "depends": ["iber_edonusum"],
    "data": [
        "views/ubl_invoice_status_views.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}
