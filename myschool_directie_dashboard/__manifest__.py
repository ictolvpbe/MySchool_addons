{
    'name': 'Directie Dashboard',
    'version': '0.1',
    'summary': 'Overzicht per leerkracht: activiteiten, professionalisering, drukwerk en uitgaven',
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': [
        'base',
        'hr',
        'myschool_core',
        'professionalisering',
        'activiteiten',
        'drukwerk',
    ],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'views/dashboard_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_directie_dashboard/static/src/css/dashboard.css',
            'myschool_directie_dashboard/static/src/js/dashboard_action.js',
            'myschool_directie_dashboard/static/src/xml/dashboard_action.xml',
        ],
    },
    'installable': True,
    'application': True,
}
