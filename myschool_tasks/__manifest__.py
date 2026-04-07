{
    'name': 'MySchool Takenbord',
    'version': '1.0',
    'category': 'MySchool',
    'summary': 'Takendashboard met procesbeheer vanuit processtemplates',
    'description': """
        MySchool Takenbord
        ==================
        * Dashboard met taken toegewezen aan gebruiker of groep
        * Start nieuwe processen vanuit processtemplates (Process Composer)
        * Kanban-stijl takenbeheer met drag-and-drop statuswijzigingen
        * Integratie met Process Composer voor templatebeheer
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'mail', 'myschool_core', 'myschool_processcomposer'],
    'data': [
        'security/taskboard_security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/process_instance_views.xml',
        'views/process_task_views.xml',
        'views/taskboard_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_tasks/static/src/css/taskboard.css',
            'myschool_tasks/static/src/js/taskboard.js',
            'myschool_tasks/static/src/xml/taskboard.xml',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
