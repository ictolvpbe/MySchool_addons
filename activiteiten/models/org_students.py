from odoo import models, fields, api


class OrgStudents(models.Model):
    _inherit = 'myschool.org'

    student_count = fields.Integer(
        string='Aantal leerlingen',
        compute='_compute_student_count',
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

    def action_view_students(self):
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        ppsbr_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        person_ids = []
        if ppsbr_type:
            rels = PropRelation.search([
                ('proprelation_type_id', '=', ppsbr_type.id),
                ('id_org', '=', self.id),
                ('id_person', '!=', False),
                ('is_active', '=', True),
            ])
            person_ids = rels.mapped('id_person').ids
        return {
            'type': 'ir.actions.act_window',
            'name': f'Leerlingen - {self.name}',
            'res_model': 'myschool.person',
            'view_mode': 'list,form',
            'domain': [('id', 'in', person_ids)],
            'context': {'create': False},
        }
