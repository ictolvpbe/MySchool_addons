{
    'name': 'Afwezigen',
    'version': '1.0',
    'summary': 'Overzicht van afwezige medewerkers door activiteiten',
    'author': 'MySchool',
    'license': 'LGPL-3',
    'category': 'MySchool',
    'depends': ['base', 'activiteiten'],
    'data': [
        'security/ir.model.access.csv',
        'views/afwezigen_views.xml',
        'views/afwezigen_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
