import base64
import csv
import io
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SCHOOLJAAR_DEFAULT = '2025-2026'


class LessenroosterImportWizard(models.TransientModel):
    _name = 'myschool_lessenrooster.import.wizard'
    _description = 'Lessenrooster Import Wizard'

    schooljaar = fields.Char(
        string='Schooljaar', required=True, default=SCHOOLJAAR_DEFAULT,
    )
    school_id = fields.Many2one(
        'myschool.org', string='School', required=True,
        default=lambda self: self.env.company.school_id or self.env.user.school_ids[:1],
    )
    file = fields.Binary(string='Bestand', required=True)
    filename = fields.Char(string='Bestandsnaam')
    replace_existing = fields.Boolean(
        string='Bestaand rooster vervangen',
        default=True,
        help='Verwijdert eerst alle bestaande lijnen voor dit schooljaar en school.',
    )

    # Result fields
    imported_count = fields.Integer(string='Geïmporteerd', readonly=True)
    skipped_count = fields.Integer(
        string='Overgeslagen (onbekende klas)', readonly=True)
    missing_klassen = fields.Text(string='Niet gevonden klassen', readonly=True)
    missing_lokalen = fields.Text(string='Niet gevonden lokalen', readonly=True)
    missing_teachers = fields.Text(string='Niet gevonden leerkrachten', readonly=True)
    state = fields.Selection([
        ('upload', 'Upload'),
        ('done', 'Klaar'),
    ], default='upload')

    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError("Upload een bestand.")

        data = base64.b64decode(self.file)
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = data.decode('latin-1')

        reader = csv.reader(io.StringIO(text))

        # Find the lln org under the selected school.
        # NB: deze import maakt GEEN org-structuur (klassen/lokalen) meer aan —
        # die hoort uit de SIS (Informat) of manueel beheer te komen, via de
        # betask-pipeline. De import koppelt enkel aan bestaande klassen/
        # lokalen en maakt de rooster-lijnen (eigen model) aan. Onbekende
        # klassen/lokalen worden gerapporteerd als waarschuwing.
        PropRelation = self.env['myschool.proprelation']

        lln_rels = PropRelation.search([
            ('id_org_parent', '=', self.school_id.id),
            ('id_org.name_short', '=', 'lln'),
        ])
        lln_org = lln_rels.mapped('id_org')[:1]

        if not lln_org:
            raise UserError(
                f"Geen 'lln' organisatie gevonden onder {self.school_id.name}. "
                "Maak eerst de leerlingen-organisatie aan."
            )

        # Look up the lokaal-parent org (niet aanmaken — optioneel).
        lokaal_rels = PropRelation.search([
            ('id_org_parent', '=', self.school_id.id),
            ('id_org.name_short', '=', 'lokaal'),
        ])
        lokaal_parent = lokaal_rels.mapped('id_org')[:1]

        # Delete existing if replacing
        if self.replace_existing:
            existing = self.env['myschool_lessenrooster.line'].search([
                ('schooljaar', '=', self.schooljaar),
                ('klas_id.id', 'in', PropRelation.search([
                    ('id_org_parent', '=', lln_org.id),
                ]).mapped('id_org').ids + [lln_org.id]),
            ])
            if existing:
                existing.unlink()
                _logger.info(f'Deleted {len(existing)} existing timetable lines')

        # Cache for lookups
        klas_cache = {}  # name -> org record
        lokaal_cache = {}  # name -> org record
        teacher_cache = {}  # abbreviation -> person record
        missing_teachers = set()
        missing_klassen = set()
        missing_lokalen = set()

        # Pre-load existing klassen under lln
        klas_rels = PropRelation.search([
            ('id_org_parent', '=', lln_org.id),
        ])
        for rel in klas_rels:
            if rel.id_org and rel.id_org.name_short:
                klas_cache[rel.id_org.name_short] = rel.id_org

        # Pre-load existing lokalen under lokaal parent (indien aanwezig)
        if lokaal_parent:
            lokaal_rels = PropRelation.search([
                ('id_org_parent', '=', lokaal_parent.id),
            ])
            for rel in lokaal_rels:
                if rel.id_org and rel.id_org.name_short:
                    lokaal_cache[rel.id_org.name_short] = rel.id_org

        # Pre-load teachers by abbreviation
        persons = self.env['myschool.person'].search([
            ('abbreviation', '!=', False),
            ('abbreviation', '!=', ''),
        ])
        for p in persons:
            teacher_cache[p.abbreviation] = p

        lines_to_create = []
        skipped_count = 0

        for row in reader:
            if len(row) < 7:
                continue
            ext_id = row[0].strip()
            klas_name = row[1].strip()
            teacher_abbr = row[2].strip()
            vak = row[3].strip()
            lokaal = row[4].strip()
            dag = row[5].strip()
            lesuur = row[6].strip()

            if not klas_name or not vak or not dag or not lesuur:
                continue

            # Klas moet bestaan (geen auto-aanmaak meer). Onbekend → skip + melden.
            klas = klas_cache.get(klas_name)
            if not klas:
                missing_klassen.add(klas_name)
                skipped_count += 1
                continue

            # Find teacher
            teacher = teacher_cache.get(teacher_abbr)
            if not teacher and teacher_abbr:
                missing_teachers.add(teacher_abbr)

            # Lokaal moet bestaan (geen auto-aanmaak). Onbekend → lijn zonder
            # lokaal + melden.
            lokaal_rec = None
            if lokaal:
                lokaal_rec = lokaal_cache.get(lokaal)
                if not lokaal_rec:
                    missing_lokalen.add(lokaal)

            lines_to_create.append({
                'schooljaar': self.schooljaar,
                'school_id': self.school_id.id,
                'external_id': int(ext_id) if ext_id.isdigit() else 0,
                'klas_id': klas.id,
                'leerkracht_id': teacher.id if teacher else False,
                'vak': vak,
                'lokaal_id': lokaal_rec.id if lokaal_rec else False,
                'dag': dag,
                'lesuur': int(lesuur) if lesuur.isdigit() else 0,
            })

        # Batch create
        if lines_to_create:
            self.env['myschool_lessenrooster.line'].create(lines_to_create)

        self.write({
            'imported_count': len(lines_to_create),
            'skipped_count': skipped_count,
            'missing_klassen': ', '.join(sorted(missing_klassen)) if missing_klassen else '',
            'missing_lokalen': ', '.join(sorted(missing_lokalen)) if missing_lokalen else '',
            'missing_teachers': ', '.join(sorted(missing_teachers)) if missing_teachers else '',
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
