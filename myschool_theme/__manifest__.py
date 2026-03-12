{
    'name': 'MySchool Theme',
    'summary': 'Teal-based backend theme for MySchool',
    'version': '19.0.1.0.0',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'MySchool',
    'depends': [
        'muk_web_theme',
    ],
    'post_init_hook': 'post_init_hook',
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            (
                'after',
                'muk_web_theme/static/src/scss/colors.scss',
                'myschool_theme/static/src/scss/colors.scss',
            ),
        ],
        'web.assets_backend': [
            'myschool_theme/static/src/scss/layout.scss',
            'myschool_theme/static/src/scss/components.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
