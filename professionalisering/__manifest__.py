{
    'name': 'Professionalisering',
    'version': '1.0',
    'summary': 'Beheer van professionaliseringsaanvragen voor leerkrachten',
    'description': """
        Module voor het beheren van professionaliseringsaanvragen.
        Leerkrachten dienen aanvragen in voor binnenschoolse, buitenschoolse
        of externe opleidingen. De directie keurt goed of af,
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
        'views/professionalisering_views.xml',
        'views/professionalisering_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
