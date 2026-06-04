{
    'name': 'MySchool MCP Server',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Model Context Protocol server — exposes MySchool data + actions to AI assistants',
    'description': """
        MySchool MCP Server
        ===================
        Geïntegreerde MCP-server (Streamable HTTP transport) als Odoo-module.

        Stelt MySchool-data en -acties beschikbaar voor AI-assistenten zoals
        Claude Code via het Model Context Protocol. Auth gebeurt via Odoo's
        native res.users.apikeys — elke gebruiker hangt een eigen API-key
        aan zijn account zodat acties in chatter onder zijn naam verschijnen.

        Providers (per myschool-module één bestand):
        * AppFoundry — projecten, items, sprints, releases (v1)
        * Later: betask, sys_event, sap_sync, ...
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'myschool_core', 'myschool_appfoundry'],
    'data': [
        'security/mcp_security.xml',
        'security/ir.model.access.csv',
        'data/sys_event_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
