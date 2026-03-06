{
    'name': 'MySchool Asset Management',
    'version': '19.0.1.0.0',
    'category': 'MySchool',
    'summary': 'Asset management for school environments',
    'description': """
        MySchool Asset Management
        =========================
        Comprehensive asset management for schools including:
        * Hardware, software, and furniture tracking
        * License management with seat tracking
        * Asset checkout/return workflow
        * Depreciation calculation
        * Warranty and license expiry notifications
        * Barcode support
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': ['myschool_core', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/asset_category_data.xml',
        'views/asset_category_views.xml',
        'views/asset_asset_views.xml',
        'views/asset_license_views.xml',
        'views/asset_checkout_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
