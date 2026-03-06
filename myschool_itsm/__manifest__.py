{
    'name': 'MySchool IT Service Management',
    'version': '19.0.1.0.0',
    'category': 'MySchool',
    'summary': 'ITIL 4 compliant IT Service Management for school environments',
    'description': """
        MySchool IT Service Management
        ===============================
        Comprehensive ITIL 4 compliant ITSM module including:
        * Incident and Service Request management
        * Problem management with root cause analysis
        * Change management with approval workflows
        * Configuration Management Database (CMDB)
        * SLA tracking and enforcement
        * Knowledge base
        * Continual improvement register
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': ['myschool_core', 'myschool_asset', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/itsm_data.xml',
        'data/mail_template_data.xml',
        'views/itsm_service_category_views.xml',
        'views/itsm_service_views.xml',
        'views/itsm_sla_views.xml',
        'views/itsm_ticket_views.xml',
        'views/itsm_problem_views.xml',
        'views/itsm_change_views.xml',
        'views/itsm_ci_views.xml',
        'views/itsm_knowledge_views.xml',
        'views/itsm_improvement_views.xml',
        'views/itsm_config_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
