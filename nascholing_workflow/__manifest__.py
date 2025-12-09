{
    'name': 'Nascholing Workflow',
    'version': '1.0',
    'summary': 'Beheer van nascholingsaanvragen voor leerkrachten',
    'description': """
        Module voor het beheren van nascholingsaanvragen door leerkrachten.
        Leerkrachten kunnen aanvragen indienen, de directie kan deze goed- of afkeuren,
        en er worden automatische e-mails verstuurd.
    """,
    'author': 'Mark Demeyer',
    'website': 'https://www.example.com',
    'category': 'Human Resources',
    'depends': ['base', 'mail', 'hr'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/mail_template_data.xml',
        'data/mail_activity_data.xml',
        'views/nascholing_aanvraag_views.xml',
        'views/nascholing_aanvraag_templates.xml',
        'views/nascholing_aanvraag_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

