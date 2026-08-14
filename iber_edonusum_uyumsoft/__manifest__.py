{
    "name": "IberoDoo Uyumsoft e-Transformation Integrator",
    "summary": "Uyumsoft e-Invoice/e-Archive integration — Uyumsoft provider for the iber_edonusum framework",
    "version": "19.0.1.7.0",
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
