"""Backend voor de 'Mijn lessenrooster — inhaalplanning'-view.

Een Owl client-action haalt z'n data via deze methods op:
  - get_grid_data(week_start) → de week van de ingelogde leerkracht
                                 met markering per gemiste les
  - get_free_slots(klas_id, date_from, date_to)
                              → lijst van datum+lesuur waar leerkracht én klas vrij zijn
  - create_inhaal(klas_id, date, lesuur, gemiste_les_id)
                              → maakt planner.record + notificatie naar beheerder
"""

from datetime import date, datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_DAY_KEY = {0: '1', 1: '2', 2: '3', 3: '4', 4: '5'}
_DAY_NAME = {'1': 'Maandag', '2': 'Dinsdag', '3': 'Woensdag',
             '4': 'Donderdag', '5': 'Vrijdag'}


class LessenroosterInhaalView(models.AbstractModel):
    """Stateless backend voor de inhaalplanning-grid.
    Geen DB-records — enkel methods aangesproken via RPC."""
    _name = 'lessenrooster.inhaal.view'
    _description = 'Lessenrooster inhaalplanning — backend'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_person(self):
        """Geeft de myschool.person van de ingelogde gebruiker terug."""
        return self.env['myschool.person'].search(
            [('odoo_user_id', '=', self.env.uid)], limit=1)

    def _current_employee(self):
        person = self._current_person()
        return person.odoo_employee_id if person else self.env['hr.employee']

    def _absence_dates_for(self, employee, klas):
        """Geeft een dict {date: {'leerkracht': [...]|None, 'klas': [...]|None}}
        terug voor afwezigheden van employee én klas in een ruim venster.

        leerkracht: lijst van bron-records (activiteit/prof titel).
        klas: lijst van bron-activiteiten."""
        result = {}
        person = employee and self.env['myschool.person'].search(
            [('odoo_employee_id', '=', employee.id)], limit=1)

        # Leerkracht via activiteiten
        if person:
            acts = self.env['activiteiten.record'].sudo().search([
                ('state', 'in', ('approved', 's_code', 'vervanging', 'done')),
                ('leerkracht_ids', 'in', [person.id]),
                ('datetime', '!=', False),
            ])
            for act in acts:
                start = act.datetime.date()
                end = (act.datetime_end or act.datetime).date()
                cur = start
                while cur <= end:
                    bucket = result.setdefault(
                        cur, {'leerkracht': [], 'klas': []})
                    bucket['leerkracht'].append({
                        'type': 'activiteit',
                        'titel': act.titel or act.name,
                    })
                    cur += timedelta(days=1)

        # Leerkracht via professionalisering
        if employee and 'professionalisering.record' in self.env:
            profs = self.env['professionalisering.record'].sudo().search([
                ('state', 'in', ('bevestiging', 'bewijs', 'done')),
                '|',
                ('employee_id', '=', employee.id),
                ('invite_ids.employee_id', '=', employee.id),
            ])
            for pr in profs:
                if not pr.start_date:
                    continue
                end_date = pr.end_date or pr.start_date
                cur = pr.start_date
                while cur <= end_date:
                    bucket = result.setdefault(
                        cur, {'leerkracht': [], 'klas': []})
                    bucket['leerkracht'].append({
                        'type': 'professionalisering',
                        'titel': pr.titel or pr.name,
                    })
                    cur += timedelta(days=1)

        # Klas via activiteiten
        if klas:
            acts = self.env['activiteiten.record'].sudo().search([
                ('state', 'in', ('approved', 's_code', 'vervanging', 'done')),
                ('klas_ids', 'in', [klas.id]),
                ('datetime', '!=', False),
            ])
            for act in acts:
                start = act.datetime.date()
                end = (act.datetime_end or act.datetime).date()
                cur = start
                while cur <= end:
                    bucket = result.setdefault(
                        cur, {'leerkracht': [], 'klas': []})
                    bucket['klas'].append({
                        'type': 'activiteit',
                        'titel': act.titel or act.name,
                    })
                    cur += timedelta(days=1)

        return result

    # ------------------------------------------------------------------
    # RPC methods (called from Owl)
    # ------------------------------------------------------------------

    @api.model
    def get_grid_data(self, week_start_str):
        """Returns:
        {
          leerkracht: {id, name},
          week_start: 'YYYY-MM-DD',
          days: [{key, name, date}],
          lesuren: [1, 2, 3, ...],
          lessons: [{
            id, dag, lesuur, klas_id, klas_name, vak, lokaal_name,
            leerkracht_name,
            missed_self: true/false,
            missed_class: true/false,
            missed_date: 'YYYY-MM-DD',
            missed_reasons: [{type, titel, who: 'leerkracht'|'klas'}],
          }],
        }"""
        week_start = fields.Date.from_string(week_start_str)
        # Naar maandag normaliseren
        if week_start.weekday() != 0:
            week_start = week_start - timedelta(days=week_start.weekday())

        person = self._current_person()
        employee = person.odoo_employee_id if person else self.env['hr.employee']
        if not person:
            return {
                'error': 'Geen gekoppelde myschool.person voor deze gebruiker.',
            }

        Line = self.env['lessenrooster.line']
        lines = Line.search([('leerkracht_id', '=', person.id)])

        # Verzamel afwezigheden voor de hele week (voor leerkracht én voor
        # alle klassen die de leerkracht heeft)
        klas_ids = set(lines.mapped('klas_id').ids)
        absences_by_date = {}
        # Leerkracht-afwezigheid (eenmalig)
        lk_absences = self._absence_dates_for(employee, None)
        for d, info in lk_absences.items():
            absences_by_date.setdefault(d, {'leerkracht': [], 'klas': {}})
            absences_by_date[d]['leerkracht'] = info['leerkracht']
        # Klas-afwezigheden (per klas)
        for klas_id in klas_ids:
            klas = self.env['myschool.org'].browse(klas_id)
            klas_absences = self._absence_dates_for(None, klas)
            for d, info in klas_absences.items():
                absences_by_date.setdefault(d, {'leerkracht': [], 'klas': {}})
                absences_by_date[d]['klas'].setdefault(klas_id, [])
                absences_by_date[d]['klas'][klas_id].extend(info['klas'])

        days = []
        for i in range(5):
            d = week_start + timedelta(days=i)
            days.append({
                'key': str(i + 1),
                'name': _DAY_NAME[str(i + 1)],
                'date': fields.Date.to_string(d),
            })

        all_uren = sorted(set(lines.mapped('lesuur')))

        lessons_data = []
        for line in lines:
            day_idx = int(line.dag) - 1
            actual_date = week_start + timedelta(days=day_idx)
            absence = absences_by_date.get(actual_date, {
                'leerkracht': [], 'klas': {}})
            missed_self = bool(absence['leerkracht'])
            klas_absences = absence['klas'].get(line.klas_id.id, [])
            missed_class = bool(klas_absences)
            reasons = []
            for r in absence['leerkracht']:
                reasons.append({
                    'who': 'leerkracht',
                    'type': r['type'],
                    'titel': r['titel'],
                })
            for r in klas_absences:
                reasons.append({
                    'who': 'klas',
                    'type': r['type'],
                    'titel': r['titel'],
                })
            lessons_data.append({
                'id': line.id,
                'dag': line.dag,
                'lesuur': line.lesuur,
                'klas_id': line.klas_id.id,
                'klas_name': line.klas_id.name_short or line.klas_id.name or '',
                'vak': line.vak or '',
                'lokaal_name': line.lokaal_id and (line.lokaal_id.name_short or line.lokaal_id.name) or '',
                'leerkracht_name': line.leerkracht_id.name or '',
                'missed_self': missed_self,
                'missed_class': missed_class,
                'missed_date': fields.Date.to_string(actual_date),
                'missed_reasons': reasons,
            })

        return {
            'leerkracht': {
                'id': person.id,
                'name': person.name or '',
                'employee_id': employee.id if employee else False,
            },
            'week_start': fields.Date.to_string(week_start),
            'week_end': fields.Date.to_string(week_start + timedelta(days=4)),
            'days': days,
            'lesuren': all_uren,
            'lessons': lessons_data,
        }

    @api.model
    def get_free_slots(self, klas_id, date_from_str, date_to_str):
        """Returns list of {date, lesuur, day_key, day_name} where leerkracht
        AND klas are both free, EN waar geen ander inhaal-record (planner.record)
        al ingepland is voor die klas of leerkracht op dat moment."""
        if not klas_id:
            return []
        date_from = fields.Date.from_string(date_from_str)
        date_to = fields.Date.from_string(date_to_str)
        if date_to < date_from:
            return []

        person = self._current_person()
        if not person:
            return []
        klas = self.env['myschool.org'].browse(klas_id)
        if not klas.exists():
            return []

        # Verzamel reeds-ingeplande inhaal-momenten in het venster, voor zowel
        # de huidige klas als de huidige leerkracht. We sluiten dergelijke
        # slots uit de suggesties zodat geen dubbele boeking mogelijk is.
        booked_slots = set()  # set of (date, lesuur)
        if 'planner.record' in self.env:
            employee = person.odoo_employee_id
            domain = [
                ('inhaal_date', '>=', date_from),
                ('inhaal_date', '<=', date_to),
                ('state', '!=', 'cancelled'),
                '|',
                ('klas_id', '=', klas.id),
                ('leerkracht_id', '=', employee.id) if employee
                    else ('id', '=', False),
            ]
            bookings = self.env['planner.record'].sudo().search(domain)
            for b in bookings:
                if not b.inhaal_date:
                    continue
                for ts in b.tijdslot_ids:
                    booked_slots.add((b.inhaal_date, ts.sequence))

        Line = self.env['lessenrooster.line']
        suggestions = []
        cur = date_from
        max_iter = 100
        i = 0
        while cur <= date_to and i < max_iter:
            i += 1
            wd = cur.weekday()
            day_key = _DAY_KEY.get(wd)
            if not day_key:
                cur += timedelta(days=1)
                continue
            day_lines = Line.search([('dag', '=', day_key)])
            all_uren = sorted(set(day_lines.mapped('lesuur')))
            busy_lk = set(day_lines.filtered(
                lambda l: l.leerkracht_id == person).mapped('lesuur'))
            busy_klas = set(day_lines.filtered(
                lambda l: l.klas_id == klas).mapped('lesuur'))
            for uur in all_uren:
                if uur in busy_lk or uur in busy_klas:
                    continue
                if (cur, uur) in booked_slots:
                    continue  # al een inhaal-aanvraag op dit moment
                suggestions.append({
                    'date': fields.Date.to_string(cur),
                    'lesuur': uur,
                    'day_key': day_key,
                    'day_name': _DAY_NAME[day_key],
                })
            cur += timedelta(days=1)
        return suggestions

    @api.model
    def create_inhaal(self, klas_id, date_str, lesuur, gemiste_les_id=None):
        """Maakt een planner.record aan voor een inhaalmoment.
        Stuurt notificatie naar group_planner_admin via mail.activity.

        Self-service flow: gebruikt sudo() omdat de aanvragende leerkracht
        géén directe access op planner.tijdslot of planner.record nodig heeft —
        het systeem maakt het record namens hen aan."""
        if 'planner.record' not in self.env:
            raise UserError(
                "Module 'planner' is niet geïnstalleerd — kan geen "
                "inhaalmoment aanmaken.")
        person = self._current_person()
        if not person or not person.odoo_employee_id:
            raise UserError(
                "Geen gekoppelde leerkracht voor deze gebruiker.")
        employee = person.odoo_employee_id

        klas = self.env['myschool.org'].browse(klas_id)
        if not klas.exists():
            raise UserError("Klas bestaat niet.")

        inhaal_date = fields.Date.from_string(date_str)
        tijdslot = self.env['planner.tijdslot'].sudo().search(
            [('sequence', '=', lesuur)], limit=1)

        # Conflict-check: bestaat er al een inhaal-record voor dezelfde
        # klas OF dezelfde leerkracht op dit (datum, lesuur)?
        if tijdslot:
            existing_domain = [
                ('inhaal_date', '=', inhaal_date),
                ('tijdslot_ids', 'in', tijdslot.ids),
                ('state', '!=', 'cancelled'),
                '|',
                ('klas_id', '=', klas.id),
                ('leerkracht_id', '=', employee.id),
            ]
            conflict = self.env['planner.record'].sudo().search(
                existing_domain, limit=1)
            if conflict:
                conflict_who = (
                    'die klas' if conflict.klas_id == klas
                    else 'die leerkracht'
                )
                raise UserError(
                    f"Er staat al een inhaalmoment ingepland op "
                    f"{inhaal_date.strftime('%d/%m/%Y')} lesuur {lesuur} "
                    f"voor {conflict_who} ({conflict.name}). "
                    f"Kies een ander moment.")

        # Optionele context vanuit gemiste les
        titel_extra = ''
        if gemiste_les_id:
            les = self.env['lessenrooster.line'].sudo().browse(gemiste_les_id)
            if les.exists():
                titel_extra = f' — {les.vak} ({les.klas_id.name_short})'

        vals = {
            'titel': f'Inhaal {employee.name}{titel_extra}',
            'leerkracht_id': employee.id,
            'klas_id': klas.id,
            'inhaal_date': inhaal_date,
        }
        if tijdslot:
            vals['tijdslot_ids'] = [(6, 0, tijdslot.ids)]
        record = self.env['planner.record'].sudo().create(vals)

        # Notificatie naar leden van group_planner_admin
        admin_group = self.env.ref(
            'planner.group_planner_admin', raise_if_not_found=False)
        if admin_group and admin_group.user_ids:
            activity_type = self.env.ref(
                'mail.mail_activity_data_todo', raise_if_not_found=False)
            for user in admin_group.user_ids:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary=f'Nieuw inhaalmoment: {record.name}',
                    note=(
                        f'<p><b>{employee.name}</b> heeft een inhaalmoment '
                        f'aangevraagd voor klas <b>{klas.name_short or klas.name}</b>.</p>'
                        f'<p>Datum: {inhaal_date.strftime("%d/%m/%Y")} — Lesuur {lesuur}</p>'
                        f'{("<p>Voor gemiste les: " + titel_extra.strip(" —") + "</p>") if titel_extra else ""}'
                    ),
                    user_id=user.id,
                )

        return {
            'planner_id': record.id,
            'planner_name': record.name,
        }
