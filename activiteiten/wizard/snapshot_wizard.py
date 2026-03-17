from odoo import models, fields, api


class SnapshotWizard(models.TransientModel):
    _name = 'activiteiten.snapshot.wizard'
    _description = 'Deelnemers op peildatum'

    activiteit_id = fields.Many2one('activiteiten.record', required=True)
    peildatum = fields.Date(string='Peildatum', default=fields.Date.context_today)
    snapshot_type = fields.Selection([
        ('student', 'Leerlingen'),
        ('leerkracht', 'Leerkrachten'),
    ], required=True)
    line_ids = fields.Many2many(
        'activiteiten.snapshot.line',
        compute='_compute_line_ids',
    )
    person_count = fields.Integer(compute='_compute_line_ids')

    @api.depends('peildatum', 'snapshot_type', 'activiteit_id')
    def _compute_line_ids(self):
        for wiz in self:
            if not wiz.activiteit_id or not wiz.peildatum:
                wiz.line_ids = False
                wiz.person_count = 0
                continue
            lines = wiz.activiteit_id.snapshot_line_ids.filtered(
                lambda l: l.snapshot_type == wiz.snapshot_type
                and l.date_from <= wiz.peildatum
                and (not l.date_to or l.date_to > wiz.peildatum)
            )
            wiz.line_ids = lines
            wiz.person_count = len(lines)

    def action_view_persons(self):
        """Open a list of the filtered persons."""
        person_ids = self.line_ids.mapped('person_id').ids
        label = 'Leerlingen' if self.snapshot_type == 'student' else 'Leerkrachten'
        return {
            'type': 'ir.actions.act_window',
            'name': f'{label} op {self.peildatum}',
            'res_model': 'myschool.person',
            'view_mode': 'list,form',
            'domain': [('id', 'in', person_ids)],
            'context': {'create': False},
        }
