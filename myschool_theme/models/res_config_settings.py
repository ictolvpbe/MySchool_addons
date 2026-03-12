import re
import base64

from odoo import api, fields, models
from odoo.tools import misc
from odoo.addons.base.models.assetsbundle import EXTENSIONS

LAYOUT_URL = '/myschool_theme/static/src/scss/layout.scss'
LAYOUT_BUNDLE = 'web.assets_backend'

# CSS custom property name -> ir.config_parameter key
COLOR_FIELDS = [
    ('brand_1', '--myschool-brand-1'),
    ('brand_2', '--myschool-brand-2'),
    ('brand_3', '--myschool-brand-3'),
    ('brand_4', '--myschool-brand-4'),
    ('text', '--myschool-text'),
    ('text_muted', '--myschool-text-muted'),
    ('bg', '--myschool-bg'),
    ('bg_card', '--myschool-bg-card'),
    ('border', '--myschool-border'),
    ('border_light', '--myschool-border-light'),
    ('hover_row', '--myschool-hover-row'),
    ('hover_btn', '--myschool-hover-btn'),
    ('surface', '--myschool-surface'),
]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ms_color_brand_1 = fields.Char(string='Brand Primary')
    ms_color_brand_2 = fields.Char(string='Brand Secondary')
    ms_color_brand_3 = fields.Char(string='Brand Accent 1')
    ms_color_brand_4 = fields.Char(string='Brand Accent 2')
    ms_color_text = fields.Char(string='Text')
    ms_color_text_muted = fields.Char(string='Text Muted')
    ms_color_bg = fields.Char(string='Background')
    ms_color_bg_card = fields.Char(string='Card Background')
    ms_color_border = fields.Char(string='Border')
    ms_color_border_light = fields.Char(string='Border Light')
    ms_color_hover_row = fields.Char(string='Row Hover')
    ms_color_hover_btn = fields.Char(string='Button Hover')
    ms_color_surface = fields.Char(string='Surface')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _ms_get_layout_content(self):
        custom_url = f'/_custom/{LAYOUT_BUNDLE}{LAYOUT_URL}'
        attachment = self.env['ir.attachment'].search([
            ('url', '=', custom_url)
        ], limit=1)
        if attachment:
            return base64.b64decode(attachment.datas).decode('utf-8')
        with misc.file_open(LAYOUT_URL.strip('/'), 'rb', filter_ext=EXTENSIONS) as f:
            return f.read().decode('utf-8')

    def _ms_get_color_values(self):
        content = self._ms_get_layout_content()
        values = {}
        for field_suffix, css_var in COLOR_FIELDS:
            match = re.search(
                rf'{re.escape(css_var)}\s*:\s*([^;]+);',
                content,
            )
            if match:
                values[field_suffix] = match.group(1).strip()
        return values

    def _ms_detect_change(self):
        current = self._ms_get_color_values()
        return any(
            self[f'ms_color_{suffix}'] != current.get(suffix)
            for suffix, _ in COLOR_FIELDS
        )

    def _ms_replace_colors(self):
        content = self._ms_get_layout_content()
        for field_suffix, css_var in COLOR_FIELDS:
            value = self[f'ms_color_{field_suffix}']
            if value:
                content = re.sub(
                    rf'({re.escape(css_var)}\s*:\s*)[^;]+(;)',
                    rf'\g<1>{value}\2',
                    content,
                )
        custom_url = f'/_custom/{LAYOUT_BUNDLE}{LAYOUT_URL}'
        datas = base64.b64encode(content.encode('utf-8'))
        attachment = self.env['ir.attachment'].search([
            ('url', '=', custom_url)
        ], limit=1)
        if attachment:
            attachment.write({'datas': datas})
            self.env.registry.clear_cache('assets')
        else:
            asset_url = LAYOUT_URL.lstrip('/')
            target_asset = self.env['ir.asset'].search([
                ('path', 'like', asset_url)
            ], limit=1)
            self.env['ir.attachment'].create({
                'name': 'layout.scss',
                'type': 'binary',
                'mimetype': 'text/scss',
                'datas': datas,
                'url': custom_url,
            })
            asset_values = {
                'path': custom_url,
                'target': LAYOUT_URL,
                'directive': 'replace',
            }
            if target_asset:
                asset_values['name'] = '%s override' % target_asset.name
                asset_values['bundle'] = target_asset.bundle
                asset_values['sequence'] = target_asset.sequence
            else:
                asset_values['name'] = 'myschool layout override'
                asset_values['bundle'] = LAYOUT_BUNDLE
            self.env['ir.asset'].create(asset_values)

    def _ms_reset_colors(self):
        custom_url = f'/_custom/{LAYOUT_BUNDLE}{LAYOUT_URL}'
        self.env['ir.attachment'].search([
            ('url', '=', custom_url)
        ]).unlink()
        self.env['ir.asset'].search([
            ('path', 'like', custom_url)
        ]).unlink()

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_reset_myschool_colors(self):
        self._ms_reset_colors()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    # ----------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------

    def get_values(self):
        res = super().get_values()
        colors = self._ms_get_color_values()
        for suffix, _ in COLOR_FIELDS:
            res[f'ms_color_{suffix}'] = colors.get(suffix, '')
        return res

    def set_values(self):
        res = super().set_values()
        if self._ms_detect_change():
            self._ms_replace_colors()
        return res
