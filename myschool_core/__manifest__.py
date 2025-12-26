{
    'name': 'MySchool Core Module',
    'version': '0.1',
    'category': 'Education',
    'summary': 'Manage school organizations, persons, roles, and periods',
    'description': """
        School Management System
        ========================
        This module provides comprehensive management of:
        * Organizations and Organization Types
        * Persons and Person Types
        * Roles and Role Types
        * Periods and Period Types
        * Relations between persons, roles, organizations and periods
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        # Securityaccount_analytic_applicability
        'security/myschool_security.xml',
        'security/ir.model.access.csv',

        # Views - Types first (dependencies)
        # 'views/main_views.xml',
        # 'views/org_type_views.xml',
        # 'views/person_type_views.xml',
        # 'views/role_type_views.xml',
        # 'views/period_type_views.xml',
        # 'views/proprelation_type_views.xml',
        # 'views/ci_relation_views.xml',

        # Views - Main models
        # 'views/org_views.xml',
        # 'views/person_views.xml',
        # 'views/person_details_views.xml',
        # 'views/role_views.xml',
        # 'views/period_views.xml',
        # 'views/proprelation_views.xml',
        # 'views/config_item_views.xml',
        # 'views/betask_views.xml',
        # 'views/sys_event_views.xml',
        # 'views/sys_event_type_views.xml',
        # 'views/betask_type_views.xml',
        # 'views/betask_views.xml',
        # 'views/informat_service_config_views.xml',

        # Menus
        # 'views/menu_views.xml',

        #demo data
        'data/sequence.xml',
        'data/sys_event_data.xml',

        #Services
        #'services/data/ir_cron_data.xml',


    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}

