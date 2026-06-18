from odoo import models, fields


class AppfoundryIconConfig(models.Model):
    _name = 'appfoundry.icon.config'
    _description = 'Icon Generator Standaardkleuren'

    name = fields.Char(default='Standaardkleuren', readonly=True)
    main_color = fields.Char(string='Hoofdkleur', default='#007d8c')
    accent_color = fields.Char(string='Accentkleur', default='#00C4D9')
    icon_style = fields.Selection(
        [('shapes', 'Kleurrijk (gevuld)'), ('line', 'Lijn (calm-tech)')],
        string='Stijl', default='shapes',
        help='Kleurrijke gevulde vorm, of een monochrome lijn-glyph op een '
             'effen tegel (calm-tech).')

    def _get_defaults(self):
        """Get the singleton config record, create if needed."""
        config = self.search([], limit=1)
        if not config:
            config = self.create({})
        return config

    def action_apply_all_menu_icons(self):
        """(Her)pas het menu-icoon van ELK actief app-project toe, elk met zijn
        eigen opgeslagen stijl/kleur/module.

        Bedoeld om na een upgrade op een andere Odoo-instance alle app-menu-
        iconen te herstellen: ``web_icon_data`` op ``ir.ui.menu`` zit in de DB,
        niet in de modulebestanden, dus na een upgrade staan de menu's weer op
        hun standaard-icoon tot ze opnieuw toegepast worden.
        """
        return self._apply_all_menu_icons(force_style=False)

    def action_force_style_all_menu_icons(self):
        """Zet ELK actief app-project op de config-stijl (``icon_style``) en
        past het meteen toe → in één klik een uniforme nav-stijl (bv. overal
        de calm-tech lijn-stijl). De per-project kleuren blijven behouden.
        """
        return self._apply_all_menu_icons(force_style=True)

    def _apply_all_menu_icons(self, force_style=False):
        self.ensure_one()
        projects = self.env['appfoundry.project'].sudo().search(
            [('is_active', '=', True)])
        applied = 0
        for project in projects:
            module = (project.icon_module_name or project.code or '').strip()
            if not module:
                continue
            if force_style and project.icon_style != self.icon_style:
                project.icon_style = self.icon_style
            project.action_apply_icon_to_menu()
            applied += 1
        if force_style:
            style_label = dict(self._fields['icon_style'].selection).get(
                self.icon_style, self.icon_style)
            message = ('%s app-menu-icoon(en) op stijl "%s" gezet. Hard refresh '
                       '(Ctrl+Shift+R) om ze te zien.' % (applied, style_label))
        else:
            message = ('%s app-menu-icoon(en) (her)toegepast. Hard refresh '
                       '(Ctrl+Shift+R) om ze te zien.' % applied)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Menu-iconen toegepast',
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }
