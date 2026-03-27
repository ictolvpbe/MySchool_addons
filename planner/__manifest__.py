{
    'name': 'Planner',
    'version': '1.0',
    'summary': 'Inhaalplannen voor klassen die afwezig waren door activiteiten',
    'description': """
        Plan inhaalmomenten voor klassen die een activiteit hebben gemist.
    """,
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'mail', 'myschool_admin', 'activiteiten'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/tijdslot_data.xml',
        'views/planner_views.xml',
        'views/vervanging_line_views.xml',
        'views/afwezige_leerkracht_views.xml',
        'views/org_inherit_views.xml',
        'views/planner_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
