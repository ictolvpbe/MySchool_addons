{
    'name': 'MySchool Theme — OLVP',
    'summary': 'OLVP-gebrande calm-tech look: petrol/teal #007E8C op warm ivoor.',
    'description': """
MySchool Theme — OLVP
=====================

OLVP-gebrande overlay die de **calm-tech** re-skin (``myschool_theme_calm``)
terugbrengt naar de **echte OLVP-merkkleur**: petrol/teal **#007E8C** als
primair, op warm ivoor (#FBFAF6), met saliegroen als secundair accent, klei
als waarschuwing en lila strikt gereserveerd voor AI.

Bron: het design-handoff ``design_handoff/calm tech olvp/``. Dit is de
OLVP-pendant van de merk-neutrale ``myschool_theme_calm``:

  myschool_theme            (basis, teal-tokens + structuur)
    └── myschool_theme_calm (calm-tech, merk-neutraal: salie/crème/lila)
          └── myschool_theme_olvp   (DEZE — zelfde calm-tech vorm, OLVP-petrol)

Installeren  → calm-tech-look in OLVP-petrol actief.
Verwijderen  → de merk-neutrale calm-tech (salie) komt terug; nog een laag
               eraf → de teal-basis ``myschool_theme``.

Token-overlay: herdefinieert enkel de design-tokens (palet → petrol/ivoor/salie/
klei/lila + exacte handoff-hexes) en flipt de paar interactie-regels die calm in
salie hardcodeerde naar petrol. Alle structurele SCSS/JS/XML (navbar-, sidebar-,
apps-menu-gedrag, typografie, radii, schaduwen) wordt hergebruikt.
    """,
    'version': '19.0.1.0.0',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'OLVP',
    'depends': [
        'myschool_theme_calm',
        # Voor de settings-tab: erft de primary view myschool_settings_form
        # en plaatst de OLVP-kleuren naast "MySchool Theme" in het scherm.
        'myschool_admin',
    ],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        # SCSS primary-variable overrides ($o-brand → petrol). Laadt NA de
        # calm-overlay zodat petrol op salie wint op compile-time.
        'web._assets_primary_variables': [
            (
                'after',
                'myschool_theme_calm/static/src/scss/colors.scss',
                'myschool_theme_olvp/static/src/scss/colors.scss',
            ),
        ],
        # Token- + selector-overlay. Laadt NA calm.scss zodat de petrol-tokens
        # en de petrol-interactie-regels de salie-versie overschrijven.
        'web.assets_backend': [
            (
                'after',
                'myschool_theme_calm/static/src/scss/calm.scss',
                'myschool_theme_olvp/static/src/scss/olvp.scss',
            ),
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
