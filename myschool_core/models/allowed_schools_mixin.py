from odoo import models, fields, api


class AllowedSchoolsMixin(models.AbstractModel):
    """Voorziet records van een lijst toegestane school-ids voor de huidige
    gebruiker/company. Gebruikt in domain-filters op school_id-velden.

    Gebruik in een model:
        class MyModel(models.Model):
            _name = 'my.model'
            _inherit = ['my.other.mixin', 'myschool.allowed.schools.mixin']
            school_id = fields.Many2one(
                'myschool.org', domain="[('id', 'in', allowed_school_json)]",
            )
    """
    _name = 'myschool.allowed.schools.mixin'
    _description = 'Allowed schools per user (mixin)'

    allowed_school_json = fields.Json(compute='_compute_allowed_school_json')

    @api.depends_context('uid', 'company')
    def _compute_allowed_school_json(self):
        schools = self.env.company.school_id or self.env.user.school_ids
        ids = schools.ids or self.env['myschool.org'].sudo().search(
            [('org_type_id.name', '=', 'SCHOOL'), ('is_active', '=', True)]
        ).ids
        for record in self:
            record.allowed_school_json = ids
