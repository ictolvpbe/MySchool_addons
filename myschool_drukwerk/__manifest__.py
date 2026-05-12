{
    'name': 'Afdrukcentrum',
    'version': '5.1',
    'summary': 'Aanvragen van myschool_drukwerk per leerling/klas voor doorrekening op factuur',
    'description': """
        Het aanvragen van myschool_drukwerk per leerling in klas dat er na wordt
        doorgerekend bij hun factuur.
    """,
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'mail', 'myschool_core'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/drukwerk_rules.xml',
        'data/sequence.xml',
        'data/cron.xml',
        'data/mail_template_data.xml',
        'views/drukwerk_views.xml',
        'views/drukwerk_config_views.xml',
        'views/drukwerk_report_views.xml',
        'wizard/student_select_wizard_views.xml',
        'wizard/print_confirm_wizard_views.xml',
        'wizard/extra_klas_wizard_views.xml',
        'wizard/count_e_export_wizard_views.xml',
        'views/drukwerk_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_drukwerk/static/src/js/drukwerk_cog_menu.js',
            'myschool_drukwerk/static/src/js/drukwerk_print_action.js',
            'myschool_drukwerk/static/src/xml/drukwerk_cog_menu.xml',
            'myschool_drukwerk/static/src/scss/myschool_drukwerk.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
