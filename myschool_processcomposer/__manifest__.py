{
    'name': 'Myschool Process Composer',
    'version': '0.156',
    'category': 'MySchool',
    'summary': 'BPMN-like business process composing with prompt generation',
    'description': """
        Myschool Process Composer
        =========================
        Visual business process composing tool with:
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
        'security/processcomposer_security.xml',
        'security/ir.model.access.csv',
        'data/sapsync_overview_process.xml',
        #'data/activiteiten_process_data.xml',
        'views/myschool_process_views.xml',
        'views/processcomposer_client_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_processcomposer/static/src/css/processcomposer.css',
            'myschool_processcomposer/static/src/js/processcomposer_canvas.js',
            'myschool_processcomposer/static/src/xml/processcomposer_canvas.xml',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
