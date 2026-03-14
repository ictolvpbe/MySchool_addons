{
    'name': 'H5P Learning',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Interactive H5P content for learning paths and assessments',
    'description': """
        H5P Learning
        =============
        Integrates H5P interactive content into Odoo:
        * Upload .h5p content packages
        * Organise content in learning paths
        * Play content via h5p-standalone (client-side)
        * Track learner results via xAPI
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/learning_path_views.xml',
        'views/h5p_content_views.xml',
        'views/h5p_result_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
