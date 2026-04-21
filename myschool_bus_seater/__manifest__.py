{
    'name': 'Bus Seater',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'School bus seating management',
    'description': """
        Bus Seater
        ==========
        Manage school bus seating arrangements:
        * Define buses with seat layouts
        * Create and manage bus routes with stops
        * Assign students to specific seats
        * Visual seat map overview
        * Track boarding and drop-off stops
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'myschool_core'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'views/bus_views.xml',
        'views/route_views.xml',
        'views/assignment_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
