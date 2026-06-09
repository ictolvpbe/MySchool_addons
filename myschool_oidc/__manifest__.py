{
    'name': 'MySchool OIDC (Keycloak)',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Keycloak-login (OIDC code-flow) voor MySchool app-instances: '
               'provider-config + maatwerk (geen JIT, link bestaande users, '
               'groepsmapping)',
    'description': """
        MySchool OIDC
        =============
        Maatwerk bovenop OCA ``auth_oidc`` zodat MySchool app-instances via
        Keycloak inloggen (SPEC-2026-AUTH-OIDC-ODOO).

        Blok B (deze versie):
        * Provider-config-laag: een (uitgeschakeld) seed-provider voor de
          dev-realm ``olvp-dev`` / client ``odoo-myschool-dev2`` als
          startpunt. Client-secret wordt per-instance in de UI ingevuld
          (staat NIET in git).
        * auth_oauth-gotcha's: systeemparam
          ``auth_oauth.authorization_header=True``.

        Roadmap (nog te doen):
        * C. Login = email-claim -> res.users.login.
        * D. Geen JIT: link aan bestaande res.users (email -> sam -> employee_id).
        * E. Gelinkte user = internal (base.group_user).
        * F. Groepsmapping groups-claim -> res.groups.
    """,
    'author': 'OLVP ICT',
    'website': 'https://github.com/ictolvpbe/MySchool_addons',
    'license': 'LGPL-3',
    'depends': ['auth_oidc'],
    'data': [
        'data/ir_config_parameter.xml',
        'data/auth_oauth_provider.xml',
    ],
    'installable': True,
    'application': False,
}
