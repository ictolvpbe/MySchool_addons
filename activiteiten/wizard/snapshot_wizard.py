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
        compute='_compute_data',
    )
    live_person_ids = fields.Many2many(
        'myschool.person',
        compute='_compute_data',
    )
    is_live_preview = fields.Boolean(compute='_compute_data')
    person_count = fields.Integer(compute='_compute_data')

    @api.depends('peildatum', 'snapshot_type', 'activiteit_id')
    def _compute_data(self):
        for wiz in self:
            wiz.line_ids = False
            wiz.live_person_ids = False
            wiz.is_live_preview = False
            wiz.person_count = 0
            if not wiz.activiteit_id or not wiz.peildatum:
                continue
            lines = wiz.activiteit_id.snapshot_line_ids.filtered(
                lambda l: l.snapshot_type == wiz.snapshot_type
                and l.date_from <= wiz.peildatum
                and (not l.date_to or l.date_to > wiz.peildatum)
            )
            if lines:
                wiz.line_ids = lines
                wiz.person_count = len(lines)
            else:
                # Geen snapshot beschikbaar (bv. activiteit nog niet ingediend)
                # → toon live data o.b.v. huidige klassen / leerkrachten.
                if wiz.snapshot_type == 'student':
                    persons = wiz.activiteit_id._get_current_students()
                else:
                    persons = wiz.activiteit_id.leerkracht_ids
                wiz.live_person_ids = persons
                wiz.is_live_preview = True
                wiz.person_count = len(persons)

    def action_view_persons(self):
        """Open a list of the filtered persons."""
        if self.line_ids:
            person_ids = self.line_ids.mapped('person_id').ids
        else:
            person_ids = self.live_person_ids.ids
        label = 'Leerlingen' if self.snapshot_type == 'student' else 'Leerkrachten'
        return {
            'type': 'ir.actions.act_window',
            'name': f'{label} op {self.peildatum}',
            'res_model': 'myschool.person',
            'view_mode': 'list,form',
            'domain': [('id', 'in', person_ids)],
            'context': {'create': False},
        }
