{
    'name': 'Process Mapper',
    'version': '0.1',
    'category': 'Productivity',
    'summary': 'BPMN-like business process mapping with prompt generation',
    'description': """
        Process Mapper
        ==============
        Visual business process mapping tool with:
        * SVG drag-and-drop canvas editor
        * BPMN-like elements (start/end events, tasks, gateways, swimlanes)
        * Integration with MySchool organizations and roles
        * Prompt generation for Odoo addon creation from approved processes
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'myschool_core'],
    'data': [
        'security/process_mapper_security.xml',
        'security/ir.model.access.csv',
        'views/process_map_views.xml',
        'views/process_mapper_client_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'process_mapper/static/src/css/process_mapper.css',
            'process_mapper/static/src/js/process_mapper_canvas.js',
            'process_mapper/static/src/xml/process_mapper_canvas.xml',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
