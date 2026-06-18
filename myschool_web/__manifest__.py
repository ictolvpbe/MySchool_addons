{
    'name': 'MySchool Web — Gedeelde UI-componenten',
    'summary': 'Herbruikbare, merk-neutrale OWL-componenten voor de MySchool-apps',
    'description': """
MySchool Web — Gedeelde UI-componenten
======================================

Een **lichte, merk-neutrale frontend-base**: enkel herbruikbare OWL-componenten
(zoals ``SegmentNav``), géén visuele theme en géén data-models. Apps die een
gedeelde component gebruiken hangen af van **deze** module — niet van een theme.

Token-gedreven: de componenten lezen de gedeelde ``--ms-*`` design-tokens **met
fallback-waarden**. Zonder een theme renderen ze dus in neutrale fallback-kleuren
(volledig functioneel); is er een theme geïnstalleerd (bv. ``myschool_theme`` of
de calm-tech overlay), dan nemen ze automatisch die design-tokens over —
in light én dark.

Afhankelijk van enkel ``web``. Een theme is nooit verplicht.
""",
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'license': 'LGPL-3',
    'author': 'MySchool',
    'depends': [
        'web',
    ],
    'assets': {
        'web.assets_backend': [
            'myschool_web/static/src/scss/components/segment_nav.scss',
            'myschool_web/static/src/components/segment_nav/segment_nav.js',
            'myschool_web/static/src/components/segment_nav/segment_nav.xml',
            'myschool_web/static/src/scss/components/icon.scss',
            'myschool_web/static/src/components/icon/icon.js',
            'myschool_web/static/src/components/icon/icon.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
