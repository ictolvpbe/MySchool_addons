{
    'name': 'Kosten Dashboard',
    'version': '1.5',
    'summary': 'Overzicht van kosten per medewerker (activiteiten en professionalisering)',
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'hr', 'myschool_core', 'myschool_dashboard'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/kosten_dashboard_data.xml',
        'views/kosten_dashboard_views.xml',
        'views/kosten_dashboard_main_views.xml',
        'views/kosten_dashboard_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'kosten_dashboard/static/src/css/kosten_dashboard.css',
            'kosten_dashboard/static/src/js/kosten_dashboard_action.js',
            'kosten_dashboard/static/src/xml/kosten_dashboard_action.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
