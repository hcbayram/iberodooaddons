{
    'name': 'Pazaryeri Yönetim Merkezi',
    'version': '19.0.1.0.0',
    'summary': 'Tüm pazaryeri connector\'larını tek çatı altında yöneten hub addon',
    'author': 'Iber Bilisim',
    'website': 'https://www.iberbilisim.com.tr',
    'category': 'eCommerce',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/marketplace_security.xml',
        'security/ir.model.access.csv',
        'views/channel_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
