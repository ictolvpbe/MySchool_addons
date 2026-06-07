{
    'name': 'MySchool Server Manager',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Beheer van Odoo-instances/servers: register, rollen, enrollment',
    'description': """
        MySchool Server Manager
        =======================
        App om de MySchool Odoo-instances/servers te beheren.

        v0.1 (fundament):
        * Server/Instance-register (SRVMGR-2): netwerk- & connectiegegevens,
          FQDN, environment (prod/test/dev), db/instance-id, rol.
        * Server-rollen samengesteld uit eigenschappen (SRVMGR-3): een rol is
          een herbruikbare bundel van capabilities (eigenschappen), niet een
          vaste enum.
        * Data-locatie & privacy (SRVMGR-4): per server per data-domein lokaal
          of via API bij een bronserver.
        * Enrollment o.b.v. rol (SRVMGR-5): idempotent taal/modules/admin-pw
          toepassen op een remote instance via de Odoo externe API (JSON-RPC).

        Roadmap (zie AppFoundry SRVMGR):
        * SRVMGR-6 Provisioning base-data + default user.
        * SRVMGR-7 myschool_sync-beheer verhuizen vanuit myschool_admin.
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'myschool_core'],
    'data': [
        'security/myschool_servermanager_security.xml',
        'security/ir.model.access.csv',
        'views/server_property_views.xml',
        'views/server_role_views.xml',
        'views/data_domain_views.xml',
        'views/server_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
