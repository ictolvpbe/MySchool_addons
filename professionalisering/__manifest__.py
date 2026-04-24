{
    'name': 'Professionalisering',
    'version': '1.4',
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
        'views/professionalisering_views.xml',
        'views/professionalisering_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
