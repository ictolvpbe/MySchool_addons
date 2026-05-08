"""Wizard om historische nascholingen uit het oude intranet-systeem te
importeren via een phpMyAdmin XML-export.

Mapping:
- aanvraagID    -> legacy_id (traceerbaarheid + rollback-handle)
- naam + email  -> employee_id (lookup via work_email of user_id.email)
- aanvraagdat   -> create_date (NIET overschreven; informatie zit in chatter)
- vak           -> vak_id (lookup of auto-create)
- onderwerp     -> titel
- datum         -> start_date (en end_date wanneer leeg)
- beginuur      -> start_uur (Float)
- einduur       -> eind_uur (Float)
- instantie     -> address_id.organization (lookup of auto-create)
- plaats        -> address_id.city
- collega       -> description (vrije tekst)
- prijs         -> total_cost (informatief)
- vervoer       -> vervoersmiddel
- opmerkingen   -> motivatie_aanleiding
- evalmotiv     -> motivatie_doelstelling
- goedkeuring   -> state ('done' bij 1, 'weigering' bij 2)

Records zonder match op employee worden geskipt en gelogd in een rapport.
"""

import base64
import io
import logging
import re
import xml.etree.ElementTree as ET

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# Mapping van oude vervoer-strings naar nieuwe vervoersmiddel-keuzes
_VERVOER_MAP = {
    'auto': 'auto_alleen',
    'trein': 'trein',
    'bus': 'ov',
    'fiets': 'fiets',
    'nvt': False,
    '': False,
}

# Mapping goedkeuring (uit oud systeem) naar state
_STATE_MAP = {
    '1': 'done',        # goedgekeurd & afgerond
    '2': 'weigering',   # afgekeurd
}


class ProfessionaliseringImportWizard(models.TransientModel):
    _name = 'professionalisering.import.wizard'
    _description = 'Import historische nascholingen'

    file_data = fields.Binary(
        string='Bestand (XML)',
        required=True,
        help='phpMyAdmin XML-export van de intranet_nascholing tabel.',
    )
    file_name = fields.Char(string='Bestandsnaam')
    skip_existing = fields.Boolean(
        string='Bestaande overslaan',
        default=True,
        help='Records met een legacy_id die al bestaat in de database '
             'overslaan (voor herhaaldelijke uploads).',
    )
    summary = fields.Text(
        string='Resultaat',
        readonly=True,
    )

    def action_import(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Upload een XML-bestand.'))

        # Decode + clean control characters die XML niet aanvaardt
        raw = base64.b64decode(self.file_data)
        cleaned = re.sub(rb'[\x00-\x08\x0B\x0C\x0E-\x1F]', b'', raw)
        try:
            tree = ET.parse(io.BytesIO(cleaned))
        except ET.ParseError as e:
            raise UserError(_('XML niet valide: %s') % e)
        root = tree.getroot()

        records_data = []
        for tbl in root.iter('table'):
            rec = {col.get('name'): (col.text or '').strip() for col in tbl}
            if rec.get('aanvraagID'):
                records_data.append(rec)

        result = self._import_records(records_data)
        self.summary = result
        # Toon de wizard opnieuw met het samenvattingsveld ingevuld
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'professionalisering.import.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _import_records(self, records_data):
        """Voert de eigenlijke import uit en retourneert een tekstrapport."""
        Prof = self.env['professionalisering.record'].sudo()
        Employee = self.env['hr.employee'].sudo()
        Vak = self.env['professionalisering.vak'].sudo()
        Address = self.env['professionalisering.address'].sudo()

        existing_legacy = set()
        if self.skip_existing:
            existing_legacy = set(
                Prof.search([('legacy_id', '!=', False)]).mapped('legacy_id')
            )

        # Caches om dubbele lookups te vermijden
        emp_cache = {}      # email_lower -> employee
        vak_cache = {}      # name_lower -> vak
        addr_cache = {}     # (org_lower, city_lower) -> address

        created = 0
        skipped_no_emp = 0
        skipped_existing = 0
        errors = 0
        error_samples = []
        no_employee_emails = set()

        for rec in records_data:
            try:
                legacy_id = rec.get('aanvraagID') or ''
                if not legacy_id:
                    continue
                if legacy_id in existing_legacy:
                    skipped_existing += 1
                    continue

                # Employee lookup via email
                email = (rec.get('email') or '').strip().lower()
                if not email or '@' not in email:
                    skipped_no_emp += 1
                    continue
                emp = emp_cache.get(email)
                if emp is None:
                    emp = Employee.search([
                        '|',
                        ('work_email', '=ilike', email),
                        ('user_id.login', '=ilike', email),
                    ], limit=1)
                    emp_cache[email] = emp
                if not emp:
                    skipped_no_emp += 1
                    no_employee_emails.add(email)
                    continue

                # Vak: lookup of auto-create
                vak_name = rec.get('vak', '').strip()
                vak = False
                if vak_name:
                    key = vak_name.lower()
                    vak = vak_cache.get(key)
                    if vak is None:
                        vak = Vak.search([('name', '=ilike', vak_name)], limit=1)
                        if not vak:
                            vak = Vak.create({'name': vak_name})
                        vak_cache[key] = vak

                # Address: lookup of auto-create
                org = (rec.get('instantie') or '').strip()
                plaats = (rec.get('plaats') or '').strip()
                addr = False
                if org or plaats:
                    addr_key = (org.lower(), plaats.lower())
                    addr = addr_cache.get(addr_key)
                    if addr is None:
                        domain = []
                        if org:
                            domain.append(('organization', '=ilike', org))
                        if plaats:
                            domain.append(('city', '=ilike', plaats))
                        addr = Address.search(domain, limit=1) if domain else False
                        if not addr:
                            addr_vals = {
                                'name': org or plaats or 'Onbekend',
                                'organization': org or False,
                                'city': plaats or False,
                            }
                            addr = Address.create(addr_vals)
                        addr_cache[addr_key] = addr

                # Datum + uren
                start_date = self._parse_date(rec.get('datum'))
                start_uur = self._parse_hour(rec.get('beginuur'))
                eind_uur = self._parse_hour(rec.get('einduur'))

                duur = 'hele_dag'
                if start_uur and eind_uur:
                    if eind_uur <= 12.5:
                        duur = 'voormiddag'
                    elif start_uur >= 12.0:
                        duur = 'namiddag'

                state = _STATE_MAP.get(rec.get('goedkeuring', ''), 'done')

                opmerkingen = rec.get('opmerkingen', '').replace('<br />', '\n').strip()
                evalmotiv = rec.get('evalmotiv', '').replace('<br />', '\n').strip()
                collega = rec.get('collega', '').strip()
                description_parts = []
                if collega:
                    description_parts.append(f'Collega(\'s) mee: {collega}')
                desc = '\n'.join(description_parts) if description_parts else False

                vals = {
                    'legacy_id': legacy_id,
                    'type': 'individueel',
                    'subtype_individueel': 'nascholing',
                    'titel': (rec.get('onderwerp') or 'Nascholing')[:200],
                    'employee_id': emp.id,
                    'vak_id': vak.id if vak else False,
                    'address_id': addr.id if addr else False,
                    'location_type': 'address',
                    'start_date': start_date,
                    'end_date': start_date,
                    'duur': duur,
                    'start_uur': start_uur or 0.0,
                    'eind_uur': eind_uur or 0.0,
                    'state': state,
                    'description': desc,
                    'motivatie_aanleiding': opmerkingen or False,
                    'motivatie_doelstelling': evalmotiv or False,
                    'vervoersmiddel': _VERVOER_MAP.get(rec.get('vervoer', ''), False),
                }

                # Prijs (oud was Integer in cents? Of euros? In schema int(5),
                # waarschijnlijk hele euros). Zetten als s_code_price voor admin-zicht.
                try:
                    prijs = int(rec.get('prijs', '0') or 0)
                    if prijs:
                        vals['s_code_price'] = float(prijs)
                except (ValueError, TypeError):
                    pass

                # School: pak standaard de eerste school van de gebruiker
                if emp.user_id and emp.user_id.school_ids:
                    vals['school_id'] = emp.user_id.school_ids[0].id

                # Maak het record aan met name='New' zodat sequence triggert
                Prof.with_context(tracking_disable=True).create(vals)
                created += 1
                # Commit per 100 om geheugen + lock-tijd te beperken
                if created % 100 == 0:
                    self.env.cr.commit()
                    _logger.info('[import] %d records aangemaakt...', created)

            except Exception as e:
                errors += 1
                if len(error_samples) < 10:
                    error_samples.append(
                        f'  aanvraagID {rec.get("aanvraagID", "?")}: {e}'
                    )
                _logger.warning('Failed to import legacy nascholing %s: %s',
                                rec.get('aanvraagID', '?'), e, exc_info=True)

        self.env.cr.commit()

        # Bouw rapport
        lines = [
            f'IMPORT KLAAR',
            f'================================',
            f'Aangemaakt           : {created}',
            f'Overgeslagen (bestond): {skipped_existing}',
            f'Overgeslagen (geen lkr): {skipped_no_emp}',
            f'Fouten               : {errors}',
            f'',
        ]
        if no_employee_emails:
            lines.append(
                f'Onbekende e-mailadressen ({len(no_employee_emails)}):'
            )
            for e in sorted(no_employee_emails)[:30]:
                lines.append(f'  - {e}')
            if len(no_employee_emails) > 30:
                lines.append(f'  ... en {len(no_employee_emails) - 30} meer')
            lines.append('')
        if error_samples:
            lines.append('Foutvoorbeelden (max 10):')
            lines.extend(error_samples)
        return '\n'.join(lines)

    @staticmethod
    def _parse_date(s):
        """'2013-10-15' -> date object. Returnt False bij ongeldig."""
        if not s or s in ('0000-00-00',):
            return False
        try:
            return fields.Date.from_string(s)
        except Exception:
            return False

    @staticmethod
    def _parse_hour(s):
        """'14:30' -> 14.5. Returnt 0.0 bij ongeldig of leeg."""
        if not s:
            return 0.0
        s = s.strip().replace('.', ':')
        m = re.match(r'^(\d{1,2}):(\d{2})', s)
        if not m:
            return 0.0
        try:
            h = int(m.group(1))
            mn = int(m.group(2))
            if 0 <= h <= 23 and 0 <= mn <= 59:
                return h + mn / 60.0
        except ValueError:
            pass
        return 0.0


class ProfessionaliseringImportRollback(models.TransientModel):
    """Rollback-wizard: verwijder alle records die via import zijn binnengekomen."""
    _name = 'professionalisering.import.rollback'
    _description = 'Rollback historische import'

    legacy_count = fields.Integer(
        string='Aantal geïmporteerde records',
        compute='_compute_legacy_count',
    )

    @api.depends()
    def _compute_legacy_count(self):
        for rec in self:
            rec.legacy_count = self.env['professionalisering.record'].search_count(
                [('legacy_id', '!=', False)]
            )

    def action_rollback(self):
        self.ensure_one()
        records = self.env['professionalisering.record'].sudo().search(
            [('legacy_id', '!=', False)]
        )
        n = len(records)
        records.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rollback voltooid'),
                'message': _('%s historische records verwijderd.') % n,
                'type': 'success',
                'sticky': False,
            },
        }
