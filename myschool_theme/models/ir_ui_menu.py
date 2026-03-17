from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Auto-generate icons for newly created root menus (app menus)
        app_menus = records.filtered(lambda m: not m.parent_id)
        if app_menus:
            try:
                self.env['myschool_theme.icon.manager']._generate_icons_for_menus(app_menus)
            except Exception:
                pass  # Don't break module install if icon generation fails
        return records
