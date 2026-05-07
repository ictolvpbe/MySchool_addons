{
    'name': 'MySchool Core Module',
    'version': '0.6',
    'category': 'MySchool',
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
        * LDAP/Active Directory integration
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail','hr'],
    'external_dependencies': {
        'python': ['ldap3', 'google-api-python-client', 'google-auth', 'weasyprint'],
    },
    'post_init_hook': '_migrate_legacy_group_flags_post_init',
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
        'data/config_item_data.xml',
        #'data/users_data.xml',
        # 'data/ldap_task_types.xml',
        'data/cloud_task_types.xml',
        'data/cloud_cron.xml',
        'data/company_sync_cron.xml',
        'data/letter_task_types.xml',
        'data/letter_template_data.xml',
        # report/letter_report_templates.xml — dropped in v0.5
        # (replaced by direct WeasyPrint rendering, see letter_template.render_pdf)

        #Services
        #'services/data/ir_cron_data.xml',

        # User form extension
        'views/res_users_views.xml',

        # Google Workspace integration
        'views/google_workspace_config_views.xml',

        # Letter templates
        'views/letter_template_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_core/static/src/webclient/**/*',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}

