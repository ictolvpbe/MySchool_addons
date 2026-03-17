from odoo import models, fields


class ActiviteitenSnapshotLine(models.Model):
    _name = 'activiteiten.snapshot.line'
    _description = 'Activiteiten Deelnemer Snapshot'
    _order = 'snapshot_type, person_name'

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
