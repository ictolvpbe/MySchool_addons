{
    'name': 'Lessenrooster',
    'version': '1.0',
    'category': 'MySchool',
    'summary': 'Lessenrooster beheer en import',
    'author': 'MySchool OLVP',
    'license': 'LGPL-3',
    'depends': ['base', 'myschool_core'],
    'data': [
        'security/ir.model.access.csv',
        'security/lessenrooster_rules.xml',
        'views/lessenrooster_views.xml',
        'wizard/import_wizard_views.xml',
        'views/lessenrooster_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
