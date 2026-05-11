"""Override van hr.employee.display_name zodat dropdowns en tags overal de
volledige "Voornaam Achternaam" tonen.

Bron van de naam (in volgorde van prioriteit):
  1. De gelinkte ``myschool.person`` (via e-mail-match) — daar zit
     ``first_name`` apart, dus we kunnen netjes "Voornaam Achternaam"
     samenstellen.
  2. Het ``hr.employee.name``-veld zelf, intelligent opgesplitst:
     - "Achternaam, Voornaam" → "Voornaam Achternaam"
     - Iets anders → laat staan zoals het is.

Werkt zowel voor ``hr.employee`` als ``hr.employee.public`` (laatste erft van
hr.employee in standaard Odoo).
"""

from odoo import api, models


def _format_full_name(first_name, last_name):
    """Combineer voornaam + achternaam tot "Voornaam Achternaam"."""
    if not first_name:
        return last_name or ''
    if ',' in (last_name or ''):
        last_name = last_name.split(',', 1)[0].strip()
    return f'{first_name} {last_name}'.strip()


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.depends('name', 'work_email')
    def _compute_display_name(self):
        # Bouw eerst een email→person cache zodat we niet per record een
        # search hoeven te doen.
        emails = {(e.work_email or '').strip().lower() for e in self if e.work_email}
        person_by_email = {}
        if emails:
            persons = self.env['myschool.person'].sudo().search([
                ('odoo_user_id.login', 'in', list(emails)),
            ])
            for p in persons:
                login = (p.odoo_user_id.login or '').strip().lower()
                if login:
                    person_by_email[login] = p
        for record in self:
            email = (record.work_email or '').strip().lower()
            person = person_by_email.get(email)
            if person and person.first_name:
                record.display_name = _format_full_name(
                    person.first_name, person.name)
                continue
            # Fallback: split "Achternaam, Voornaam" naar "Voornaam Achternaam"
            raw = (record.name or '').strip()
            if ',' in raw:
                last, first = [p.strip() for p in raw.split(',', 1)]
                if first:
                    record.display_name = f'{first} {last}'
                    continue
            record.display_name = raw
