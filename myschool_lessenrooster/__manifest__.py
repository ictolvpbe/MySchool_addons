{
    'name': 'Lessenrooster',
    'version': '1.1',
    'category': 'MySchool',
    'summary': 'Lessenrooster beheer en import',
    'author': 'MySchool OLVP',
    'license': 'LGPL-3',
    # Inhaalplanning-flow vereist myschool_planner & myschool_activiteiten op runtime — maar
    # we declareren géén harde dependency om circular imports te vermijden
    # (myschool_planner zelf hangt af van myschool_lessenrooster). Runtime-check in inhaal_view.py.
    'depends': ['base', 'myschool_core'],
    'data': [
        'security/ir.model.access.csv',
        'security/lessenrooster_rules.xml',
        'views/lessenrooster_views.xml',
        'wizard/import_wizard_views.xml',
        'views/inhaal_views.xml',
        'views/lessenrooster_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_lessenrooster/static/src/scss/inhaal_grid.scss',
            'myschool_lessenrooster/static/src/js/inhaal_grid.js',
            'myschool_lessenrooster/static/src/xml/inhaal_grid.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
