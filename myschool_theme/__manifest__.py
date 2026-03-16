{
    'name': 'MySchool Theme',
    'summary': 'Teal-based backend theme for MySchool',
    'version': '19.0.2.0.0',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'MySchool',
    'depends': [
        'web',
        'base_setup',
    ],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            (
                'after',
                'web/static/src/scss/primary_variables.scss',
                'myschool_theme/static/src/scss/colors.scss',
            ),
        ],
        'web.assets_backend': [
            'myschool_theme/static/src/scss/layout.scss',
            'myschool_theme/static/src/scss/components.scss',
            'myschool_theme/static/src/scss/appsmenu.scss',
            'myschool_theme/static/src/scss/navbar.scss',
            'myschool_theme/static/src/xml/navbar.xml',
            'myschool_theme/static/src/js/appsmenu.js',
            'myschool_theme/static/src/js/navbar.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
