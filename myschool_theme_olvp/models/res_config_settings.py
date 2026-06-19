# ============================================================================
# MySchool Theme — OLVP · instelbare kerntokens via res.config.settings
# ----------------------------------------------------------------------------
# Spiegelt het mechanisme van myschool_theme (layout.scss): leest de CSS-
# custom-properties uit de LIGHT :root van olvp.scss en schrijft bij wijziging
# een /_custom/…/olvp.scss override-attachment (via een ir.asset 'replace'-
# directive). olvp.scss wint wanneer de OLVP-overlay actief is, dus dit is het
# juiste bestand om de live-kleuren van te sturen.
#
# Eén UI-veld kan meerdere CSS-vars aansturen (bv. "Achtergrond" zet zowel de
# standaard-Odoo-canvas --myschool-bg als de OWL-app-canvas --ms-surface-base).
# Enkel de LIGHT :root wordt aangepast; het dark-blok blijft onaangeroerd.
# ============================================================================
import re
import base64

from odoo import fields, models
from odoo.tools import misc
from odoo.addons.base.models.assetsbundle import EXTENSIONS

OLVP_SCSS_URL = '/myschool_theme_olvp/static/src/scss/olvp.scss'
OLVP_BUNDLE = 'web.assets_backend'

# Matcht enkel het eerste (light) :root { … }-blok; dat blok bevat geen
# geneste accolades, dus [^}]* is veilig. Het dark-blok heeft selector
# `html body[data-theme="dark"]` (geen `:root`) en wordt dus nooit geraakt.
_LIGHT_ROOT_RE = re.compile(r'(:root\s*\{)([^}]*)(\})')

# settings-veld-suffix -> lijst CSS-vars (in de light :root) die het stuurt
OLVP_COLOR_FIELDS = [
    ('primary',       ['--myschool-brand-1', '--myschool-statusbar-current']),
    ('primary_hover', ['--myschool-brand-2']),
    ('text',          ['--myschool-text']),
    ('bg',            ['--myschool-bg', '--ms-surface-base']),
    ('card',          ['--myschool-bg-card', '--ms-surface-1']),
    ('warm',          ['--ms-surface-2']),
    ('border',        ['--myschool-border']),
    ('accent_green',  ['--ms-success']),
    ('accent_clay',   ['--ms-warning']),
    ('accent_ai',     ['--ms-accent-ai']),
    ('navbar',        ['--ms-navbar-bg']),
]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    olvp_color_primary = fields.Char(string='Primair (petrol)')
    olvp_color_primary_hover = fields.Char(string='Primair hover')
    olvp_color_text = fields.Char(string='Tekst')
    olvp_color_bg = fields.Char(string='Achtergrond (ivoor)')
    olvp_color_card = fields.Char(string='Kaart-oppervlak')
    olvp_color_warm = fields.Char(string='Warm vlak')
    olvp_color_border = fields.Char(string='Rand')
    olvp_color_accent_green = fields.Char(string='Accent salie / succes')
    olvp_color_accent_clay = fields.Char(string='Accent klei / waarschuwing')
    olvp_color_accent_ai = fields.Char(string='AI-accent (lila)')
    olvp_color_navbar = fields.Char(string='Navbar')

    # ------------------------------------------------------------------
    # Helpers — lezen/schrijven van de light :root in olvp.scss
    # ------------------------------------------------------------------

    def _olvp_get_content(self):
        custom_url = f'/_custom/{OLVP_BUNDLE}{OLVP_SCSS_URL}'
        attachment = self.env['ir.attachment'].search([
            ('url', '=', custom_url)
        ], limit=1)
        if attachment:
            return base64.b64decode(attachment.datas).decode('utf-8')
        with misc.file_open(OLVP_SCSS_URL.strip('/'), 'rb', filter_ext=EXTENSIONS) as f:
            return f.read().decode('utf-8')

    def _olvp_get_color_values(self):
        content = self._olvp_get_content()
        match = _LIGHT_ROOT_RE.search(content)
        body = match.group(2) if match else ''
        values = {}
        for suffix, css_vars in OLVP_COLOR_FIELDS:
            mm = re.search(
                rf'{re.escape(css_vars[0])}\s*:\s*([^;]+);',
                body,
            )
            if mm:
                values[suffix] = mm.group(1).strip()
        return values

    def _olvp_detect_change(self):
        current = self._olvp_get_color_values()
        return any(
            self[f'olvp_color_{suffix}'] != current.get(suffix)
            for suffix, _ in OLVP_COLOR_FIELDS
        )

    def _olvp_replace_colors(self):
        content = self._olvp_get_content()
        match = _LIGHT_ROOT_RE.search(content)
        if not match:
            return
        body = match.group(2)
        for suffix, css_vars in OLVP_COLOR_FIELDS:
            value = self[f'olvp_color_{suffix}']
            if not value:
                continue
            for css_var in css_vars:
                body = re.sub(
                    rf'({re.escape(css_var)}\s*:\s*)[^;]+(;)',
                    rf'\g<1>{value}\2',
                    body,
                )
        content = content[:match.start(2)] + body + content[match.end(2):]

        custom_url = f'/_custom/{OLVP_BUNDLE}{OLVP_SCSS_URL}'
        datas = base64.b64encode(content.encode('utf-8'))
        attachment = self.env['ir.attachment'].search([
            ('url', '=', custom_url)
        ], limit=1)
        if attachment:
            attachment.write({'datas': datas})
            self.env.registry.clear_cache('assets')
        else:
            asset_url = OLVP_SCSS_URL.lstrip('/')
            target_asset = self.env['ir.asset'].search([
                ('path', 'like', asset_url)
            ], limit=1)
            self.env['ir.attachment'].create({
                'name': 'olvp.scss',
                'type': 'binary',
                'mimetype': 'text/scss',
                'datas': datas,
                'url': custom_url,
            })
            asset_values = {
                'path': custom_url,
                'target': OLVP_SCSS_URL,
                'directive': 'replace',
            }
            if target_asset:
                asset_values['name'] = '%s override' % target_asset.name
                asset_values['bundle'] = target_asset.bundle
                asset_values['sequence'] = target_asset.sequence
            else:
                asset_values['name'] = 'myschool olvp override'
                asset_values['bundle'] = OLVP_BUNDLE
            self.env['ir.asset'].create(asset_values)
            self.env.registry.clear_cache('assets')

    def _olvp_reset_colors(self):
        custom_url = f'/_custom/{OLVP_BUNDLE}{OLVP_SCSS_URL}'
        self.env['ir.attachment'].search([
            ('url', '=', custom_url)
        ]).unlink()
        self.env['ir.asset'].search([
            ('path', 'like', custom_url)
        ]).unlink()
        self.env.registry.clear_cache('assets')

    # ------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------

    def action_reset_olvp_colors(self):
        self._olvp_reset_colors()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get_values(self):
        res = super().get_values()
        colors = self._olvp_get_color_values()
        for suffix, _ in OLVP_COLOR_FIELDS:
            res[f'olvp_color_{suffix}'] = colors.get(suffix, '')
        return res

    def set_values(self):
        res = super().set_values()
        if self._olvp_detect_change():
            self._olvp_replace_colors()
        return res
