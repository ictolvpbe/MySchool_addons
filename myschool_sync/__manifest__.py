{
    'name': 'MySchool Sync',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Master-slave data replication between MySchool Odoo instances',
    'description': """
        MySchool Sync Module
        ====================
        Replicates core data (persons, orgs, roles, periods, proprelations)
        from a master Odoo instance to one or more slave instances.

        Features:
        * Configurable master/slave role via system parameter
        * Betask-based sync pipeline with retry and error handling
        * Natural key record matching (no shared database IDs)
        * Per-model and per-school sync filtering
        * Full sync and incremental sync support
        * Sync event logging on both sides
    """,
    'author': 'MySchool OLVP',
    'license': 'LGPL-3',
    'depends': ['myschool_core', 'myschool_admin'],
    'data': [
        # Security
        'security/myschool_sync_security.xml',
        'security/ir.model.access.csv',
        'security/sync_record_rules.xml',

        # Data
        'data/sync_betask_types.xml',
        'data/sync_cron.xml',

        # Views
        'views/sync_target_views.xml',
        'views/sync_log_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
