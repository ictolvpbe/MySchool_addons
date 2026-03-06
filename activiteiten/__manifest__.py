{
    'name': 'Activiteiten',
    'version': '1.0',
    'summary': 'Aanvragen voor interne en externe schoolactiviteiten',
    'description': """
        Een module voor het aanvragen van een uitstap samen met een klas of klassen
        zowel interne als externe activiteiten.
    """,
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'mail'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/activiteiten_rules.xml',
        'data/sequence.xml',
        'data/mail_template_data.xml',
        'views/activiteiten_views.xml',
        'views/activiteiten_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
