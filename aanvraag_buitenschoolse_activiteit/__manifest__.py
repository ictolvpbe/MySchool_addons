{
    'name': 'Aanvraag Buitenschoolse Activiteit',
    'version': '1.0',
    'summary': 'Beheer van aanvragen voor buitenschoolse activiteiten',
    'description': """
        Module voor het beheren van aanvragen voor buitenschoolse activiteiten.
        Medewerkers dienen aanvragen in, de directie keurt goed of af,
        en boekhouding verwerkt de betaling.
    """,
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'Human Resources',
    'depends': ['base', 'mail', 'hr'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/mail_template_data.xml',
        'views/aanvraag_buitenschoolse_activiteit_views.xml',
        'views/aanvraag_buitenschoolse_activiteit_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
