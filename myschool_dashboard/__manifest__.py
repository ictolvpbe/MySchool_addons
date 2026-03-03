{
    'name': 'Mijn Dashboard',
    'version': '1.0',
    'summary': 'Persoonlijk dashboard met overzicht van al je taken',
    'author': 'MySchool',
    'category': 'Productivity',
    'depends': ['base', 'nascholingsaanvraag', 'aanvraag_buitenschoolse_activiteit', 'professionalisering'],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'views/dashboard_menu.xml',
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
