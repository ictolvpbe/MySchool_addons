{
    'name': 'Phishing Bewustwording',
    'version': '0.1',
    'category': 'MySchool',
    'summary': 'Interne phishing bewustwordingscampagnes',
    'description': """
        Phishing Bewustwording
        ======================
        Module voor het beheren van interne phishing simulaties:
        - Campagnes aanmaken en beheren
        - E-mail sjablonen met trackingpixel
        - Doelwitten selecteren uit gebruikers
        - Klik- en rapportagestatistieken
        - Nep-inlogpagina voor bewustwording
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/phishing_security.xml',
        'security/ir.model.access.csv',
        'views/phishing_template_views.xml',
        'views/phishing_campaign_views.xml',
        'views/phishing_target_views.xml',
        'views/phishing_result_views.xml',
        'wizard/launch_campaign_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
