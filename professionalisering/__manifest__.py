{
    'name': 'Professionalisering',
    'version': '3.8',
    'summary': 'Beheer van professionaliseringsaanvragen voor leerkrachten',
    'description': """
        Module voor het beheren van professionaliseringsaanvragen.
        Leerkrachten dienen aanvragen in voor binnenschoolse, buitenschoolse
        of externe opleidingen. De directie keurt goed of af,
        boekhouding bevestigt betaling en vervangingen plant vervanging in.
    """,
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'mail', 'hr', 'myschool_core'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/professionalisering_rules.xml',
        'data/sequence.xml',
        'data/mail_template_data.xml',
        'data/cron_data.xml',
        'views/professionalisering_views.xml',
        'views/professionalisering_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'professionalisering/static/src/scss/professionalisering.scss',
            'professionalisering/static/src/js/char_filter_field.js',
            'professionalisering/static/src/xml/char_filter_field.xml',
            'professionalisering/static/src/js/address_review_notification.js',
            'professionalisering/static/src/js/activity_menu_patch.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
