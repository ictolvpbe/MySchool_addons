{
    'name': 'Drukwerk',
    'version': '1.2',
    'summary': 'Aanvragen van drukwerk per leerling/klas voor doorrekening op factuur',
    'description': """
        Het aanvragen van drukwerk per leerling in klas dat er na wordt
        doorgerekend bij hun factuur.
    """,
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'mail', 'myschool_core', 'myschool_admin'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/drukwerk_rules.xml',
        'data/sequence.xml',
        'data/cron.xml',
        'views/drukwerk_views.xml',
        'views/drukwerk_config_views.xml',
        'wizard/student_select_wizard_views.xml',
        'views/drukwerk_menu.xml',
    ],
    'assets': {},
    'installable': True,
    'application': True,
    'auto_install': False,
}
