{
    'name': 'Asset & Inventory Management',
    'version': '19.0.1.0.0',
    'category': 'MySchool',
    'summary': 'ITIL-based asset and inventory management for schools',
    'description': """
        Asset & Inventory Management (A&I)
        ====================================
        Comprehensive asset management for schools based on ITIL 4 framework:
        * Asset Types structured via hierarchical categories
        * Policy-based access control per group, asset type/category, and school
        * Asset assignment to owner (school) and user (person)
        * Room-based location linking
        * License management with seat tracking
        * Asset checkout/return workflow
        * Depreciation calculation
        * Warranty and license expiry notifications
    """,
    'author': 'MySchool OLVP',
    'license': 'LGPL-3',
    'depends': ['myschool_core', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/asset_type_category_data.xml',
        'views/asset_type_category_views.xml',
        'views/asset_type_views.xml',
        'views/asset_views.xml',
        'views/asset_license_views.xml',
        'views/asset_checkout_views.xml',
        'views/access_policy_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
