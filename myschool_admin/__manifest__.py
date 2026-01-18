{
    'name': 'MySchool Admin Module',
    'version': '0.1',
    'category': 'Education',
    'summary': 'Manage school organizations, persons, roles, periods ans services',
    'description': """
        School Management System
        ========================
        This module provides comprehensive management of: models in the myschool-core module
        * Organizations and Organization Types
        * Persons and Person Types
        * Roles and Role Types
        * Periods and Period Types
        * Relations between persons, roles, organizations and periods
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base','mail','myschool_core','web'],
    'data': [
        # Securityaccount_analytic_applicability
        'security/ir.model.access.csv',

        # Views - Types first (dependencies)
        'views/main_views.xml',
        'views/org_type_views.xml',
        'views/person_type_views.xml',
        'views/role_type_views.xml',
        'views/period_type_views.xml',
        'views/proprelation_type_views.xml',
        'views/ci_relation_views.xml',

        # Views - Main models
        'views/org_views.xml',
        'views/person_views.xml',
        'views/person_details_views.xml',
        'views/role_views.xml',
        'views/period_views.xml',
        'views/proprelation_views.xml',
        'views/config_item_views.xml',
        'views/betask_views.xml',
        'views/sys_event_views.xml',
        'views/sys_event_type_views.xml',
        'views/betask_type_views.xml',
        'views/informat_service_config_views.xml',
        # 'views/log_viewer_views.xml',
        'views/object_browser_views.xml',

        # Menus
        'views/menu_views.xml',

        #Wizards
        'views/wizard_views.xml',

        #demo data
        'data/sequence.xml',
        'data/sys_event_data.xml',

        #Services
        #'services/data/ir_cron_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_admin/static/src/css/object_browser.css',
            'myschool_admin/static/src/js/object_browser.js',
            'myschool_admin/static/src/xml/object_browser.xml',
            # 'myschool_admin/static/src/js/log_viewer.js',
            # 'myschool_admin/static/src/xml/log_viewer.xml',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}

