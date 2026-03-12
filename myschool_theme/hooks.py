import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# MySchool mockup palette
LIGHT_COLORS = [
    {'name': 'color_brand', 'value': '#007d8c'},
    {'name': 'color_primary', 'value': '#007d8c'},
    {'name': 'color_success', 'value': '#0d9488'},
    {'name': 'color_info', 'value': '#0284c7'},
    {'name': 'color_warning', 'value': '#d97706'},
    {'name': 'color_danger', 'value': '#dc2626'},
]

THEME_COLORS = [
    {'name': 'color_appsmenu_text', 'value': '#F8F9FA'},
    {'name': 'color_appbar_text', 'value': '#cce8eb'},
    {'name': 'color_appbar_active', 'value': '#0094A4'},
    {'name': 'color_appbar_background', 'value': '#004850'},
]


def post_init_hook(env):
    _logger.info('MySchool Theme: applying mockup colors to MuK settings...')
    editor = env['muk_web_colors.color_assets_editor']
    # Light mode colors
    editor.replace_color_variables_values(
        '/muk_web_colors/static/src/scss/colors_light.scss',
        'web._assets_primary_variables',
        LIGHT_COLORS,
    )
    # Theme / appbar colors
    editor.replace_color_variables_values(
        '/muk_web_theme/static/src/scss/colors.scss',
        'web._assets_primary_variables',
        THEME_COLORS,
    )
    _logger.info('MySchool Theme: colors applied successfully.')
