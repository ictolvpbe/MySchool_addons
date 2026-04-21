import base64
import csv
import io
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SCHOOLJAAR_DEFAULT = '2025-2026'


class LessenroosterImportWizard(models.TransientModel):
    _name = 'lessenrooster.import.wizard'
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
    created_klassen = fields.Integer(string='Nieuwe klassen aangemaakt', readonly=True)
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

        # Find the lln org under the selected school
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        OrgType = self.env['myschool.org.type']

        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

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

        # Find or create lokaal parent org under school
        lokaal_rels = PropRelation.search([
            ('id_org_parent', '=', self.school_id.id),
            ('id_org.name_short', '=', 'lokaal'),
        ])
        lokaal_parent = lokaal_rels.mapped('id_org')[:1]
        if not lokaal_parent:
            lokaal_parent = self.env['myschool.org'].create({
                'name': 'Lokalen',
                'name_short': 'lokaal',
                'inst_nr': lln_org.inst_nr or '000000',
                'org_type_id': dept_type.id if dept_type else False,
                'is_active': True,
            })
            if org_tree_type:
                PropRelation.create({
                    'proprelation_type_id': org_tree_type.id,
                    'id_org_parent': self.school_id.id,
                    'id_org': lokaal_parent.id,
                    'is_active': True,
                })
            _logger.info(f'Created lokaal parent org under {self.school_id.name}')

        # Delete existing if replacing
        if self.replace_existing:
            existing = self.env['lessenrooster.line'].search([
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

        # Pre-load existing klassen under lln
        klas_rels = PropRelation.search([
            ('id_org_parent', '=', lln_org.id),
        ])
        for rel in klas_rels:
            if rel.id_org and rel.id_org.name_short:
                klas_cache[rel.id_org.name_short] = rel.id_org

        # Pre-load existing lokalen under lokaal parent
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
        created_klassen = 0

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

            # Find or create klas
            klas = klas_cache.get(klas_name)
            if not klas:
                # Create new klas under lln
                klas = self.env['myschool.org'].create({
                    'name': klas_name,
                    'name_short': klas_name,
                    'inst_nr': lln_org.inst_nr or '000000',
                    'org_type_id': dept_type.id if dept_type else False,
                    'is_active': True,
                })
                # Link to lln via proprelation
                if org_tree_type:
                    PropRelation.create({
                        'proprelation_type_id': org_tree_type.id,
                        'id_org_parent': lln_org.id,
                        'id_org': klas.id,
                        'is_active': True,
                    })
                klas_cache[klas_name] = klas
                created_klassen += 1
                _logger.info(f'Created new klas: {klas_name}')

            # Find teacher
            teacher = teacher_cache.get(teacher_abbr)
            if not teacher and teacher_abbr:
                missing_teachers.add(teacher_abbr)

            # Find or create lokaal
            lokaal_rec = None
            if lokaal:
                lokaal_rec = lokaal_cache.get(lokaal)
                if not lokaal_rec:
                    lokaal_rec = self.env['myschool.org'].create({
                        'name': lokaal,
                        'name_short': lokaal,
                        'inst_nr': lln_org.inst_nr or '000000',
                        'org_type_id': dept_type.id if dept_type else False,
                        'is_active': True,
                    })
                    if org_tree_type:
                        PropRelation.create({
                            'proprelation_type_id': org_tree_type.id,
                            'id_org_parent': lokaal_parent.id,
                            'id_org': lokaal_rec.id,
                            'is_active': True,
                        })
                    lokaal_cache[lokaal] = lokaal_rec

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
            self.env['lessenrooster.line'].create(lines_to_create)

        self.write({
            'imported_count': len(lines_to_create),
            'created_klassen': created_klassen,
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
