from odoo import models, fields, api


class ActiviteitenSnapshotLine(models.Model):
    _name = 'activiteiten.snapshot.line'
    _description = 'Activiteiten Deelnemer Snapshot'
    _order = 'snapshot_type, klas_name, person_name'

    activiteit_id = fields.Many2one(
        'activiteiten.record', string='Activiteit',
        required=True, ondelete='cascade',
    )
    person_id = fields.Many2one(
        'myschool.person', string='Persoon',
        required=True, ondelete='cascade',
    )
    person_name = fields.Char(
        related='person_id.name', store=True, string='Naam',
    )
    snapshot_type = fields.Selection([
        ('student', 'Leerling'),
        ('leerkracht', 'Leerkracht'),
    ], string='Type', required=True)
    date_from = fields.Date(
        string='Vanaf',
        required=True,
        help='Datum waarop deze persoon aan de activiteit was gekoppeld.',
    )
    date_to = fields.Date(
        string='Tot',
        help='Datum waarop deze persoon niet meer gekoppeld was. Leeg = nog steeds actief.',
    )
    klas_name = fields.Char(
        string='Klas', compute='_compute_klas_name', store=True,
    )

    @api.depends('person_id', 'activiteit_id.klas_ids')
    def _compute_klas_name(self):
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        for line in self:
            if not person_tree_type or not line.person_id or not line.activiteit_id.klas_ids:
                line.klas_name = ''
                continue
            rel = PropRelation.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('id_person', '=', line.person_id.id),
                ('id_org', 'in', line.activiteit_id.klas_ids.ids),
                ('is_active', '=', True),
            ], limit=1)
            line.klas_name = rel.id_org.name if rel else ''
