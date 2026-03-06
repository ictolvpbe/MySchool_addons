{
    'name': 'Mijn Dashboard',
    'version': '1.0',
    'summary': 'Persoonlijk dashboard met overzicht van al je taken',
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'myschool_core', 'aanvraag_buitenschoolse_activiteit', 'professionalisering', 'activiteiten'],
    'data': [
        'security/ir.model.access.csv',
        'data/dashboard_data.xml',
        'data/test_users.xml',
        'views/dashboard_views.xml',
        'views/dashboard_menu.xml',
        'views/ir_module_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_dashboard/static/src/css/dashboard.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
