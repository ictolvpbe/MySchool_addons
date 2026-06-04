{
    'name': 'MySchool Projects',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Hierarchical project management with sub-projects (WBS) and progress rollup',
    'description': """
        MySchool Projects
        =================
        Generieke projectbeheer-app als aanvulling op AppFoundry (dev-gericht).

        v1 (PoC):
        * Hiërarchische projecten met sub-projecten (WBS) via parent_id/child_ids
        * Voortgang-rollup over sub-projecten
        * Chatter (mail.thread) voor audit + opvolging
        * Benaderbaar via de MySchool MCP-server (provider 'projects')

        Roadmap: milestones, gantt/timeline, baseline, budget, resource-capaciteit,
        en visuele WBS-weergave via een uitgefactoreerde GraphCanvas.
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'myschool_core'],
    'data': [
        'security/myschool_projects_security.xml',
        'security/ir.model.access.csv',
        'views/project_views.xml',
        'views/milestone_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
