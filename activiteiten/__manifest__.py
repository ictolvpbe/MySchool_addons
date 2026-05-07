{
    'name': 'Activiteiten',
    'version': '2.0',
    'summary': 'Aanvragen voor interne en externe schoolactiviteiten',
    'description': """
        Een module voor het aanvragen van een uitstap samen met een klas of klassen
        zowel interne als externe activiteiten.
    """,
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'mail', 'myschool_core', 'myschool_admin'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/activiteiten_rules.xml',
        'data/sequence.xml',
        'data/mail_template_data.xml',
        'views/bus_views.xml',
        'views/activiteiten_views.xml',
        'views/activiteiten_invite_views.xml',
        'views/activiteiten_config_views.xml',
        'views/activiteiten_menu.xml',
        'views/org_views.xml',
        'wizard/snapshot_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'activiteiten/static/src/scss/activiteiten.scss',
        ],
    },
    'post_init_hook': '_fix_missing_references',
    'installable': True,
    'application': True,
    'auto_install': False,
}
