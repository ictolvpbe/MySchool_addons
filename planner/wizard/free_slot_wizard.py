from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


# Mapping: Python weekday() (0-6, Monday=0) → lessenrooster.line.dag selectie ('1'-'5')
_DAY_KEY_FROM_WEEKDAY = {0: '1', 1: '2', 2: '3', 3: '4', 4: '5'}
_DAY_NAME = {'1': 'Maandag', '2': 'Dinsdag', '3': 'Woensdag',
             '4': 'Donderdag', '5': 'Vrijdag'}


class PlannerFreeSlotWizard(models.TransientModel):
    """Zoekt momenten waarop zowel de afwezige leerkracht als de klas vrij zijn
    (geen lessenrooster.line voor beiden op dat dag/uur)."""
    _name = 'planner.free.slot.wizard'
    _description = 'Vrij moment zoeker'

    planner_id = fields.Many2one('planner.record', required=True)
    leerkracht_id = fields.Many2one(
        'hr.employee', related='planner_id.leerkracht_id', readonly=True)
    # Voorkeur: klas opnieuw selecteerbaar in de wizard zodat de gebruiker
    # specifiek voor één klas een vrij moment kan zoeken (een leerkracht
    # heeft meestal lessen in meerdere klassen).
    klas_id = fields.Many2one(
        'myschool.org', string='Klas',
        domain="[('id', 'in', affected_klas_ids)]",
        help='Welke klas heeft les gemist en moet ingehaald worden? '
             'Default = de klas op het inhaalplan.',
    )
    affected_klas_ids = fields.Many2many(
        'myschool.org', compute='_compute_affected_klas_ids',
        string='Klassen met gemiste lessen',
    )
    search_from = fields.Date(
        string='Zoek vanaf', required=True,
        default=lambda self: fields.Date.today(),
    )
    search_until = fields.Date(
        string='Zoek tot', required=True,
        default=lambda self: fields.Date.today() + timedelta(days=14),
    )
    suggestion_ids = fields.One2many(
        'planner.free.slot.suggestion', 'wizard_id',
        string='Vrije momenten', readonly=True,
    )
    has_searched = fields.Boolean(default=False)
    no_klas_warning = fields.Boolean(compute='_compute_no_klas_warning')

    @api.depends('planner_id.gemiste_lessen_ids')
    def _compute_affected_klas_ids(self):
        for wiz in self:
            wiz.affected_klas_ids = wiz.planner_id.gemiste_lessen_ids.mapped('klas_id')

    @api.depends('klas_id')
    def _compute_no_klas_warning(self):
        for wiz in self:
            wiz.no_klas_warning = not wiz.klas_id

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        # Default klas_id uit de planner (indien aanwezig)
        planner_id = defaults.get('planner_id') or self.env.context.get('default_planner_id')
        if planner_id and 'klas_id' in fields_list:
            planner = self.env['planner.record'].browse(planner_id)
            if planner.klas_id:
                defaults['klas_id'] = planner.klas_id.id
        return defaults

    def action_search(self):
        self.ensure_one()
        self.suggestion_ids.unlink()
        if self.search_until < self.search_from:
            raise UserError("'Zoek tot' moet ná 'Zoek vanaf' liggen.")
        if not self.leerkracht_id and not self.klas_id:
            raise UserError(
                "Geen leerkracht én geen klas — minstens één is nodig om "
                "vrije momenten te zoeken.")
        if not self.klas_id:
            raise UserError(
                "Selecteer eerst een klas. Zonder klas zou de zoeker elke "
                "uur waarop de leerkracht niets staat als 'vrij' tonen — "
                "niet bruikbaar voor een inhaalmoment voor een specifieke klas.")

        Line = self.env['lessenrooster.line']
        # Map hr.employee → myschool.person voor lessenrooster
        person = (
            self.leerkracht_id
            and self.env['myschool.person'].search(
                [('odoo_employee_id', '=', self.leerkracht_id.id)], limit=1
            )
        )

        suggestions = []
        cur = self.search_from
        max_iterations = 100  # vangnet tegen oneindige loops
        i = 0
        while cur <= self.search_until and i < max_iterations:
            i += 1
            wd = cur.weekday()
            day_key = _DAY_KEY_FROM_WEEKDAY.get(wd)
            if not day_key:
                cur += timedelta(days=1)
                continue

            # Welke lesuren bestaan er op deze dag in het lessenrooster?
            day_lines = Line.search([('dag', '=', day_key)])
            all_uren = sorted(set(day_lines.mapped('lesuur')))

            # Cache busy-status per (uur)
            busy_lk = set()
            busy_klas = set(day_lines.filtered(
                lambda l: l.klas_id == self.klas_id
            ).mapped('lesuur'))
            if person:
                busy_lk = set(day_lines.filtered(
                    lambda l: l.leerkracht_id == person
                ).mapped('lesuur'))

            for uur in all_uren:
                if uur in busy_lk or uur in busy_klas:
                    continue
                suggestions.append({
                    'wizard_id': self.id,
                    'date': cur,
                    'lesuur': uur,
                    'day_key': day_key,
                    'klas_id': self.klas_id.id,
                })
            cur += timedelta(days=1)

        if suggestions:
            self.env['planner.free.slot.suggestion'].create(suggestions)
        self.has_searched = True
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class PlannerFreeSlotSuggestion(models.TransientModel):
    """Eén suggestie van een vrij moment — zelf-registreerbaar via knop."""
    _name = 'planner.free.slot.suggestion'
    _description = 'Vrij moment suggestie'
    _order = 'date, lesuur'

    wizard_id = fields.Many2one(
        'planner.free.slot.wizard', required=True, ondelete='cascade')
    date = fields.Date(string='Datum', required=True)
    lesuur = fields.Integer(string='Lesuur', required=True)
    day_key = fields.Char(string='Dag-key', help='Internal: 1-5 = Mon-Fri')
    day_name = fields.Char(
        string='Dag', compute='_compute_day_name')
    klas_id = fields.Many2one('myschool.org', string='Klas')

    @api.depends('day_key')
    def _compute_day_name(self):
        for rec in self:
            rec.day_name = _DAY_NAME.get(rec.day_key, '')

    def action_apply_to_planner(self):
        """Pas deze suggestie toe op het planner-record:
        zet inhaal_date + zoek de bijhorende tijdslot, en update klas_id
        als die nog niet ingesteld was."""
        self.ensure_one()
        planner = self.wizard_id.planner_id
        # Zoek de bijhorende tijdslot via sequence
        tijdslot = self.env['planner.tijdslot'].search(
            [('sequence', '=', self.lesuur)], limit=1)
        vals = {'inhaal_date': self.date}
        if tijdslot:
            vals['tijdslot_ids'] = [(6, 0, tijdslot.ids)]
        if self.klas_id and not planner.klas_id:
            vals['klas_id'] = self.klas_id.id
        planner.write(vals)
        return {'type': 'ir.actions.act_window_close'}
