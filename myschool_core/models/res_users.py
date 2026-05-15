from odoo import models, fields, api


class ResGroups(models.Model):
    _inherit = 'res.groups'

    module_category_name = fields.Char(
        string='Module',
        compute='_compute_module_category_name',
        search='_search_module_category_name',
    )

    @api.depends('privilege_id.category_id.name')
    def _compute_module_category_name(self):
        for group in self:
            if group.privilege_id and group.privilege_id.category_id:
                group.module_category_name = group.privilege_id.category_id.name
            else:
                group.module_category_name = ''

    def _search_module_category_name(self, operator, value):
        return [('privilege_id.category_id.name', operator, value)]

    @api.depends_context('short_display_name')
    def _compute_full_name(self):
        """Override to show category name instead of privilege name."""
        super()._compute_full_name()
        if not self.env.context.get('short_display_name'):
            for group in self:
                if group.privilege_id and group.privilege_id.category_id:
                    group.full_name = '%s / %s' % (
                        group.privilege_id.category_id.name, group.name)


class ResUsers(models.Model):
    _inherit = 'res.users'

    school_ids = fields.Many2many('myschool.org', string='Scholen')

    # Per-user voorkeur voor de SAP-sync wizard: default-waarde voor de
    # "Preview tonen voor commit"-checkbox. Beheerders die routine-syncs
    # draaien kunnen dit uitvinken; voorzichtigere admins laten het aan.
    myschool_sap_sync_always_review = fields.Boolean(
        string='Altijd SAP-sync preview tonen',
        default=True,
        help='Default voor de "Preview tonen"-checkbox in de Informat-'
             'sync wizard. Je kan dit nog steeds per run aanpassen.',
    )

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
