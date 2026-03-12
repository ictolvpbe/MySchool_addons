from odoo import models, fields, api


class OrgStudents(models.Model):
    _inherit = 'myschool.org'

    student_ids = fields.Many2many(
        'myschool.person',
        string='Leerlingen',
        compute='_compute_student_ids',
    )

    @api.depends_context('uid')
    def _compute_student_ids(self):
        PropRel = self.env['myschool.proprelation']
        for org in self:
            rels = PropRel.search([
                ('proprelation_type_id.name', '=', 'PERSON-TREE'),
                ('id_org', '=', org.id),
                ('is_active', '=', True),
            ])
            org.student_ids = rels.mapped('id_person')
