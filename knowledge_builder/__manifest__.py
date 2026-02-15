{
    'name': 'Knowledge Builder',
    'version': '0.2',
    'category': 'Productivity',
    'summary': 'Visual knowledge object builder with step editor',
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/knowledge_builder_security.xml',
        'security/ir.model.access.csv',
        'views/knowledge_object_views.xml',
        'views/knowledge_builder_client_views.xml',
        'views/share_template.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'knowledge_builder/static/src/css/knowledge_builder.css',
            'knowledge_builder/static/src/js/knowledge_builder_editor.js',
            'knowledge_builder/static/src/xml/knowledge_builder_editor.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
