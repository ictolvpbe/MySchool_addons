import base64
import json
import logging
import os

from odoo import models
from odoo.tools import config

from .icon_generator import generate_icon

_logger = logging.getLogger(__name__)

DEFAULT_PAIRS = [
    ('#007d8c', '#00C4D9'),   # Teal
    ('#2E7D32', '#66BB6A'),   # Green
    ('#C62828', '#EF5350'),   # Red
    ('#F57F17', '#FFCA28'),   # Amber
]

# Standard Odoo addon paths (modules here keep their original icons)
_STANDARD_PATHS = None


def _get_standard_paths():
    """Return the set of standard Odoo addons directories."""
    global _STANDARD_PATHS
    if _STANDARD_PATHS is None:
        _STANDARD_PATHS = set()
        paths = config['addons_path']
        if isinstance(paths, str):
            paths = paths.split(',')
        for path in paths:
            path = path.strip()
            if 'odoo' in path.lower() and 'extra' not in path.lower():
                _STANDARD_PATHS.add(os.path.normpath(path))
    return _STANDARD_PATHS


def _is_custom_module(module_name, env):
    """Check if a module is a custom (extra-addons) module, not standard Odoo."""
    mod = env['ir.module.module'].sudo().search([
        ('name', '=', module_name),
    ], limit=1)
    if not mod:
        return False
    # Check if the module's icon path points to extra-addons
    standard_paths = _get_standard_paths()
    paths = config['addons_path']
    if isinstance(paths, str):
        paths = paths.split(',')
    for addon_path in paths:
        addon_path = os.path.normpath(addon_path.strip() if isinstance(addon_path, str) else addon_path)
        module_dir = os.path.join(addon_path, module_name)
        if os.path.isdir(module_dir):
            return addon_path not in standard_paths
    return False


class IconManager(models.AbstractModel):
    _name = 'myschool_theme.icon.manager'
    _description = 'App Icon Manager'

    def _get_color_pairs(self):
        """Read the 4 color pairs from system parameters."""
        get = self.env['ir.config_parameter'].sudo().get_param
        pairs = []
        for i in range(1, 5):
            main = get(f'myschool_theme.icon_pair_{i}_main', DEFAULT_PAIRS[i - 1][0])
            accent = get(f'myschool_theme.icon_pair_{i}_accent', DEFAULT_PAIRS[i - 1][1])
            pairs.append((main, accent))
        return pairs

    def _get_assignments(self):
        """Read module-to-pair assignments as dict {module_name: pair_index}."""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'myschool_theme.icon_assignments', '{}')
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save_assignments(self, assignments):
        self.env['ir.config_parameter'].sudo().set_param(
            'myschool_theme.icon_assignments', json.dumps(assignments))

    def _get_next_pair(self):
        """Get the next round-robin pair index (1-4)."""
        val = self.env['ir.config_parameter'].sudo().get_param(
            'myschool_theme.icon_next_pair', '1')
        try:
            return int(val)
        except (ValueError, TypeError):
            return 1

    def _set_next_pair(self, idx):
        self.env['ir.config_parameter'].sudo().set_param(
            'myschool_theme.icon_next_pair', str(idx))

    def _get_module_for_menu(self, menu):
        """Get the module technical name for a root menu.

        Prefer xmlid (actual owning module) over web_icon field,
        since web_icon may reference a different module for the icon path.
        """
        xmlid = menu.get_external_id().get(menu.id, '')
        if xmlid and '.' in xmlid:
            return xmlid.split('.')[0]
        if menu.web_icon:
            parts = menu.web_icon.split(',')
            if parts:
                return parts[0].strip()
        return ''

    def _generate_icon_for_menu(self, menu, pair_index=None):
        """Generate and write an icon for a single root menu."""
        module_name = self._get_module_for_menu(menu)

        # Skip standard Odoo modules — keep their original icons
        if module_name and not _is_custom_module(module_name, self.env):
            return

        pairs = self._get_color_pairs()
        assignments = self._get_assignments()

        if pair_index is None:
            pair_index = assignments.get(module_name)
            if pair_index is None:
                pair_index = self._get_next_pair()
                next_idx = (pair_index % 4) + 1
                self._set_next_pair(next_idx)

        if module_name:
            assignments[module_name] = pair_index
            self._save_assignments(assignments)

        idx = max(1, min(4, pair_index)) - 1
        main_color, accent_color = pairs[idx]

        try:
            icon_bytes = generate_icon(
                main_color, accent_color,
                module_name=module_name,
                display_name=menu.name or module_name,
            )
            icon_b64 = base64.b64encode(icon_bytes)
            menu.write({'web_icon_data': icon_b64})
        except Exception:
            _logger.warning('Failed to generate icon for menu %s', menu.name, exc_info=True)

    def _generate_icons_for_menus(self, menus):
        """Auto-generate icons for multiple root menus (skips standard Odoo)."""
        for menu in menus:
            self._generate_icon_for_menu(menu)

    def _restore_standard_icons(self):
        """Restore original icons for standard Odoo modules from their SVG files."""
        root_menus = self.env['ir.ui.menu'].sudo().search([
            ('parent_id', '=', False),
        ])
        Menu = self.env['ir.ui.menu'].sudo()
        for menu in root_menus:
            module_name = self._get_module_for_menu(menu)
            if not module_name or _is_custom_module(module_name, self.env):
                continue
            # Re-compute web_icon_data from the web_icon field (e.g. "sale,static/description/icon.svg")
            if menu.web_icon and ',' in menu.web_icon:
                try:
                    icon_data = Menu._compute_web_icon_data(menu.web_icon)
                    if icon_data:
                        menu.write({'web_icon_data': icon_data})
                        _logger.info('Restored original icon for %s', module_name)
                except Exception:
                    _logger.warning('Failed to restore icon for %s', module_name, exc_info=True)

    def _regenerate_all_icons(self):
        """Regenerate icons for custom app root menus and restore standard ones."""
        # First restore any corrupted standard Odoo icons
        self._restore_standard_icons()

        root_menus = self.env['ir.ui.menu'].sudo().search([
            ('parent_id', '=', False),
        ])
        assignments = self._get_assignments()
        pairs = self._get_color_pairs()

        for menu in root_menus:
            module_name = self._get_module_for_menu(menu)

            # Skip standard Odoo modules (already restored above)
            if module_name and not _is_custom_module(module_name, self.env):
                continue

            pair_index = assignments.get(module_name)
            if pair_index is None:
                pair_index = self._get_next_pair()
                next_idx = (pair_index % 4) + 1
                self._set_next_pair(next_idx)
                if module_name:
                    assignments[module_name] = pair_index

            idx = max(1, min(4, pair_index)) - 1
            main_color, accent_color = pairs[idx]

            try:
                icon_bytes = generate_icon(
                    main_color, accent_color,
                    module_name=module_name,
                    display_name=menu.name or module_name,
                )
                icon_b64 = base64.b64encode(icon_bytes)
                menu.write({'web_icon_data': icon_b64})
            except Exception:
                _logger.warning('Failed to generate icon for menu %s', menu.name, exc_info=True)

        self._save_assignments(assignments)
        self.env.registry.clear_cache()
