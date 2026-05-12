from odoo import models, fields, api


class OrgStudents(models.Model):
    _inherit = 'myschool.org'

    student_count = fields.Integer(
        string='Aantal leerlingen',
        compute='_compute_student_count',
    )
    student_ids = fields.Many2many(
        'myschool.person',
        string='Leerlingen',
        compute='_compute_student_ids',
    )

    def _compute_student_count(self):
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        ppsbr_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        for org in self:
            if ppsbr_type:
                org.student_count = PropRelation.search_count([
                    ('proprelation_type_id', '=', ppsbr_type.id),
                    ('id_org', '=', org.id),
                    ('id_person', '!=', False),
                    ('is_active', '=', True),
                ])
            else:
                org.student_count = 0

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

    def action_view_students(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Leerlingen - {self.name}',
            'res_model': 'myschool.person',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.student_ids.ids)],
            'context': {'create': False},
        }
