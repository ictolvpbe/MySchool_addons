{
    'name': 'Bus Seater (DEPRECATED)',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'School bus seating management (deprecated)',
    'description': """
        Bus Seater (gedeactiveerd)
        ==========================
        Manage school bus seating arrangements:
        * Define buses with seat layouts
        * Create and manage bus routes with stops
        * Assign students to specific seats
        * Visual seat map overview
        * Track boarding and drop-off stops

        DEPRECATED — niet langer actief in de OLVP-flow. Busverdeling per
        uitstap zit nu in de `activiteiten`-module (`activiteiten.bus`).
        Deze module wordt op installable=False gezet zodat ze niet meer in
        Apps kan geïnstalleerd worden. Bestaande installaties blijven werken
        tot een beheerder ze manueel verwijdert.
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
    # installable=True houden zodat upgrades via myschool_core niet vastlopen
    # (cascade-upgrade van afhankelijke modules). De cleanup gebeurt via een
    # post-migrate in myschool_core 0.4 die deze module uninstall'd.
    'installable': True,
    'application': False,
    'auto_install': False,
}
