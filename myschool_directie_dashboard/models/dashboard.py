from datetime import date

from odoo import api, fields, models


def _schoolyear_start(today):
    """Return start of current Belgian schoolyear (1 sept of current or previous year)."""
    if today.month >= 9:
        return date(today.year, 9, 1)
    return date(today.year - 1, 9, 1)


def _schoolyear_end(today):
    """Return end of current Belgian schoolyear (31 aug of next or current year)."""
    if today.month >= 9:
        return date(today.year + 1, 8, 31)
    return date(today.year, 8, 31)


class MySchoolDirectieDashboard(models.Model):
    _name = 'myschool.directie.dashboard'
    _description = 'Directie Dashboard — Overzicht per leerkracht'
    _rec_name = 'employee_id'

    name = fields.Char(default='Directie Dashboard')
    employee_id = fields.Many2one('hr.employee', string='Leerkracht')
    date_from = fields.Date(
        string='Van',
        default=lambda self: _schoolyear_start(fields.Date.today()),
    )
    date_to = fields.Date(string='Tot', default=fields.Date.today)
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    # Professionalisering
    prof_count_done = fields.Integer(compute='_compute_section_data')
    prof_count_planned = fields.Integer(compute='_compute_section_data')
    prof_cost_done = fields.Monetary(compute='_compute_section_data', currency_field='currency_id')
    prof_cost_planned = fields.Monetary(compute='_compute_section_data', currency_field='currency_id')

    # Activiteiten
    act_count_done = fields.Integer(compute='_compute_section_data')
    act_count_planned = fields.Integer(compute='_compute_section_data')
    act_cost_done = fields.Monetary(compute='_compute_section_data', currency_field='currency_id')
    act_cost_planned = fields.Monetary(compute='_compute_section_data', currency_field='currency_id')

    # Drukwerk
    druk_count_done = fields.Integer(compute='_compute_section_data')
    druk_count_planned = fields.Integer(compute='_compute_section_data')
    druk_cost_done = fields.Monetary(compute='_compute_section_data', currency_field='currency_id')
    druk_cost_planned = fields.Monetary(compute='_compute_section_data', currency_field='currency_id')

    # Grand totals
    total_cost_done = fields.Monetary(compute='_compute_section_data', currency_field='currency_id')
    total_cost_planned = fields.Monetary(compute='_compute_section_data', currency_field='currency_id')

    # --- Computes ---

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_section_data(self):
        today = fields.Date.today()
        for rec in self:
            if not rec.employee_id or not rec.date_from or not rec.date_to:
                self._reset_section_data(rec)
                continue
            self._fill_prof(rec, today)
            self._fill_act(rec, today)
            self._fill_druk(rec, today)
            rec.total_cost_done = rec.prof_cost_done + rec.act_cost_done + rec.druk_cost_done
            rec.total_cost_planned = rec.prof_cost_planned + rec.act_cost_planned + rec.druk_cost_planned

    @staticmethod
    def _reset_section_data(rec):
        rec.prof_count_done = rec.prof_count_planned = 0
        rec.act_count_done = rec.act_count_planned = 0
        rec.druk_count_done = rec.druk_count_planned = 0
        rec.prof_cost_done = rec.prof_cost_planned = 0.0
        rec.act_cost_done = rec.act_cost_planned = 0.0
        rec.druk_cost_done = rec.druk_cost_planned = 0.0
        rec.total_cost_done = rec.total_cost_planned = 0.0

    def _fill_prof(self, rec, today):
        Model = self.env['professionalisering.record']
        base = [
            ('employee_id', '=', rec.employee_id.id),
            ('start_date', '>=', rec.date_from),
            ('start_date', '<=', rec.date_to),
            ('state', '!=', 'weigering'),
        ]
        done = Model.search(base + [('start_date', '<', today)])
        planned = Model.search(base + [('start_date', '>=', today)])
        rec.prof_count_done = len(done)
        rec.prof_count_planned = len(planned)
        rec.prof_cost_done = sum(r.total_cost or 0.0 for r in done)
        rec.prof_cost_planned = sum(r.total_cost or 0.0 for r in planned)

    def _fill_act(self, rec, today):
        # activiteiten.record links to myschool.person via leerkracht_ids (M2M)
        person = self.env['myschool.person'].search(
            [('odoo_employee_id', '=', rec.employee_id.id)], limit=1)
        if not person:
            rec.act_count_done = rec.act_count_planned = 0
            rec.act_cost_done = rec.act_cost_planned = 0.0
            return
        Model = self.env['activiteiten.record']
        base = [
            ('leerkracht_ids', 'in', person.id),
            ('datetime', '>=', rec.date_from),
            ('datetime', '<=', rec.date_to),
            ('state', '!=', 'rejected'),
        ]
        done = Model.search(base + [('datetime', '<', today)])
        planned = Model.search(base + [('datetime', '>=', today)])
        rec.act_count_done = len(done)
        rec.act_count_planned = len(planned)
        rec.act_cost_done = sum(r.price or 0.0 for r in done)
        rec.act_cost_planned = sum(r.price or 0.0 for r in planned)

    def _fill_druk(self, rec, today):
        Model = self.env['drukwerk.record']
        # Drukwerk uses create_uid as creator; map employee → user
        user = rec.employee_id.user_id
        if not user:
            rec.druk_count_done = rec.druk_count_planned = 0
            rec.druk_cost_done = rec.druk_cost_planned = 0.0
            return
        base = [
            ('create_uid', '=', user.id),
            ('print_deadline', '>=', rec.date_from),
            ('print_deadline', '<=', rec.date_to),
        ]
        done = Model.search(base + [('print_deadline', '<', today)])
        planned = Model.search(base + [('print_deadline', '>=', today)])
        rec.druk_count_done = len(done)
        rec.druk_count_planned = len(planned)
        rec.druk_cost_done = sum(r.total_cost or 0.0 for r in done)
        rec.druk_cost_planned = sum(r.total_cost or 0.0 for r in planned)

    # --- Quick-set actions for date range ---

    def action_set_today(self):
        for rec in self:
            rec.date_to = fields.Date.today()

    def action_set_schoolyear(self):
        today = fields.Date.today()
        for rec in self:
            rec.date_from = _schoolyear_start(today)
            rec.date_to = _schoolyear_end(today)

    # --- Drill-down actions: open filtered list per section ---

    def _open_records(self, model_name, employee_field, employee_value, date_field,
                      date_min, date_max, action_name, employee_operator='='):
        return {
            'type': 'ir.actions.act_window',
            'name': action_name,
            'res_model': model_name,
            'view_mode': 'list,form',
            'domain': [
                (employee_field, employee_operator, employee_value),
                (date_field, '>=', date_min),
                (date_field, '<=', date_max),
            ],
        }

    def action_open_prof_done(self):
        self.ensure_one()
        today = fields.Date.today()
        return self._open_records(
            'professionalisering.record', 'employee_id', self.employee_id.id,
            'start_date', self.date_from, min(self.date_to, today),
            'Professionalisering — Gedaan',
        )

    def action_open_prof_planned(self):
        self.ensure_one()
        today = fields.Date.today()
        return self._open_records(
            'professionalisering.record', 'employee_id', self.employee_id.id,
            'start_date', max(self.date_from, today), self.date_to,
            'Professionalisering — Gepland',
        )

    def _act_person(self):
        return self.env['myschool.person'].search(
            [('odoo_employee_id', '=', self.employee_id.id)], limit=1)

    def action_open_act_done(self):
        self.ensure_one()
        today = fields.Date.today()
        person = self._act_person()
        if not person:
            return False
        return self._open_records(
            'activiteiten.record', 'leerkracht_ids', person.id,
            'datetime', self.date_from, min(self.date_to, today),
            'Activiteiten — Gedaan',
            employee_operator='in',
        )

    def action_open_act_planned(self):
        self.ensure_one()
        today = fields.Date.today()
        person = self._act_person()
        if not person:
            return False
        return self._open_records(
            'activiteiten.record', 'leerkracht_ids', person.id,
            'datetime', max(self.date_from, today), self.date_to,
            'Activiteiten — Gepland',
            employee_operator='in',
        )

    def action_open_druk_done(self):
        self.ensure_one()
        today = fields.Date.today()
        user = self.employee_id.user_id
        if not user:
            return False
        return self._open_records(
            'drukwerk.record', 'create_uid', user.id,
            'print_deadline', self.date_from, min(self.date_to, today),
            'Drukwerk — Gedaan',
        )

    def action_open_druk_planned(self):
        self.ensure_one()
        today = fields.Date.today()
        user = self.employee_id.user_id
        if not user:
            return False
        return self._open_records(
            'drukwerk.record', 'create_uid', user.id,
            'print_deadline', max(self.date_from, today), self.date_to,
            'Drukwerk — Gepland',
        )
