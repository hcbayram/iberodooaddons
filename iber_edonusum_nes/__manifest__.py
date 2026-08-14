{
    "name": "IberoDoo NES e-Transformation Integrator",
    "summary": "NES e-Transformation API integration — NES provider for the iber_edonusum framework",
    "version": "19.0.1.6.0",
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
