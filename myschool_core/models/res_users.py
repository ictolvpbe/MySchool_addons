from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    school_ids = fields.Many2many('myschool.org', string='Scholen')

    @api.onchange('company_ids')
    def _onchange_company_ids_set_schools(self):
        """Auto-fill school_ids based on the schools linked to the user's companies."""
        schools = self.company_ids.mapped('school_id')
        if schools:
            self.school_ids = [(6, 0, schools.ids)]

    def write(self, vals):
        res = super().write(vals)
        if 'company_ids' in vals:
            for user in self:
                schools = user.company_ids.mapped('school_id')
                if schools:
                    user.school_ids = [(6, 0, schools.ids)]
        return res
