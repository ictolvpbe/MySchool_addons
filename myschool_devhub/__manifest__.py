{
    'name': 'DevHub',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Development project management with agile workflow',
    'description': """
        DevHub
        ======
        Development project management for MySchool with:
        * User stories, bugs, tasks, and improvements
        * Kanban board with configurable stages
        * Sprint planning and velocity tracking
        * Release management with progress tracking
        * Integration with Process Mapper for workflow linking
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'myschool_core', 'process_mapper'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/stage_data.xml',
        'data/tag_data.xml',
        'data/test_type_data.xml',
        'views/project_views.xml',
        'views/item_views.xml',
        'views/test_item_views.xml',
        'views/sprint_views.xml',
        'views/release_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_devhub/static/src/css/devhub.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
