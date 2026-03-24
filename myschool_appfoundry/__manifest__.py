{
    'name': 'AppFoundry',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Development project management with agile workflow',
    'description': """
        AppFoundry
        ======
        Development project management for MySchool with:
        * User stories, bugs, tasks, and improvements
        * Kanban board with configurable stages
        * Sprint planning and velocity tracking
        * Release management with progress tracking
        * Built-in process mapping with SVG canvas editor
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'myschool_core', 'myschool_theme'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/stage_data.xml',
        'data/tag_data.xml',
        'data/test_type_data.xml',
        'report/project_doc_reports.xml',
        'report/project_doc_templates.xml',
        'views/project_wizard_views.xml',
        'views/project_views.xml',
        'views/item_views.xml',
        'views/test_item_views.xml',
        'views/sprint_views.xml',
        'views/release_views.xml',
        'views/icon_config_views.xml',
        'views/process_map_views.xml',
        'views/process_mapper_client_views.xml',
        'data/myschool_processes.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_appfoundry/static/src/css/appfoundry.css',
            'myschool_appfoundry/static/src/css/process_mapper.css',
            'myschool_appfoundry/static/src/js/process_mapper_canvas.js',
            'myschool_appfoundry/static/src/xml/process_mapper_canvas.xml',
            'myschool_appfoundry/static/src/js/process_mapper_appfoundry.js',
            'myschool_appfoundry/static/src/xml/process_mapper_appfoundry.xml',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
