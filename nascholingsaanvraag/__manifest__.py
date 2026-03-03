{
    'name': 'Nascholingsaanvraag',
    'version': '1.8',
    'summary': 'Beheer van nascholingsaanvragen voor leerkrachten',
    'description': """
        Module voor het beheren van nascholingsaanvragen.
        Leerkrachten dienen aanvragen in, de directie keurt goed of af,
        boekhouding bevestigt betaling en vervangingen plant vervanging in.
    """,
    'author': 'MySchool',
    'category': 'Human Resources',
    'depends': ['base', 'mail', 'hr'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/mail_template_data.xml',
        'views/nascholingsaanvraag_views.xml',
        'views/nascholingsaanvraag_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'nascholingsaanvraag/static/src/css/nascholingsaanvraag.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
