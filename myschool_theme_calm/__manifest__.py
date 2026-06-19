{
    'name': 'MySchool Theme — Calm Tech',
    'summary': 'Calm-tech re-skin (crème/salie/lila-AI) — overlay op MySchool Theme',
    'description': """
MySchool Theme — Calm Tech
==========================

Een **calm-tech** herhuisstijl bovenop de bestaande ``myschool_theme`` (teal).
Overlay-aanpak: deze module *depend* op ``myschool_theme`` en herdefinieert enkel
de design-tokens — palet (warm crème / salie / lila-AI), typografie (Inter +
Plus Jakarta Sans, self-hosted), grotere radii en zachte schaduwen. Alle
structurele SCSS/JS/XML (navbar-, sidebar-, apps-menu-gedrag) wordt hergebruikt.

Installeren  → calm-tech-look actief.
Verwijderen  → de teal ``myschool_theme`` komt onveranderd terug.

Bron-ontwerp: het calm-tech design-handoff (``design_handoff_melira/``). De
technische namespace blijft merk-neutraal (tokens ``--ms-*``); dit is een
visuele exploratie, geen productie-rebrand.
""",
    'version': '19.0.1.0.0',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'MySchool',
    'depends': [
        'myschool_theme',
    ],
    'assets': {
        'web._assets_primary_variables': [
            (
                'after',
                'myschool_theme/static/src/scss/colors.scss',
                'myschool_theme_calm/static/src/scss/colors.scss',
            ),
        ],
        'web.assets_backend': [
            'myschool_theme_calm/static/src/scss/fonts.scss',
            'myschool_theme_calm/static/src/scss/calm.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
