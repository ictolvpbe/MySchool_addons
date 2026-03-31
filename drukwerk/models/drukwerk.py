import base64
import io
import logging
from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DrukwerkRecord(models.Model):
    _name = 'drukwerk.record'
    _description = 'Drukwerk Aanvraag'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Referentie',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
    drukwerk_type = fields.Selection([
        ('gewoon', 'Gewoon drukwerk'),
        ('examen', 'Examen drukwerk'),
    ], string='Type drukwerk', tracking=True)
    titel = fields.Char(string='Omschrijving')
    description = fields.Text(string='Toelichting')
    print_deadline = fields.Date(
        string='Gewenste drukdatum',
        tracking=True,
    )
    school_id = fields.Many2one(
        'myschool.org',
        string='School',
        default=lambda self: self.env.company.school_id or self.env.user.school_ids[:1],
        domain="[('id', 'in', allowed_school_json)]",
    )
    school_company_id = fields.Many2one(
        'res.company', string='Bedrijf (school)',
        compute='_compute_school_company_id', store=True,
    )
    allowed_school_json = fields.Json(
        compute='_compute_allowed_school_json',
    )
    available_klas_ids = fields.Many2many(
        'myschool.org',
        compute='_compute_available_klas_ids',
        store=False,
    )
    klas_ids = fields.Many2many(
        'myschool.org',
        'drukwerk_record_klas_rel',
        'record_id', 'org_id',
        string='Klassen',
        domain="[('id', 'in', available_klas_ids)]",
    )
    student_ids = fields.Many2many(
        'myschool.person',
        'drukwerk_record_student_rel',
        'record_id', 'person_id',
        string='Leerlingen',
    )
    # --- Document fields ---
    document_file = fields.Binary(string='Document', attachment=True)
    document_filename = fields.Char(string='Bestandsnaam')
    aantal_paginas = fields.Integer(string="Pagina's", default=1)
    aantal_kopies = fields.Integer(
        string='Kopieën',
        compute='_compute_aantal_kopies',
        store=True,
    )
    kleur = fields.Selection([
        ('zw', 'Zwart-wit'),
        ('kleur', 'Kleur'),
    ], string='Kleur', default='zw', required=True)
    formaat = fields.Selection([
        ('a4', 'A4'),
        ('a3', 'A3'),
    ], string='Formaat', default='a4', required=True)
    kopie_leerkracht = fields.Boolean(string='Kopie leerkracht', default=False)
    papier_kleur = fields.Selection([
        ('geen', 'Wit (standaard)'),
        ('groen', 'Groen'),
        ('geel', 'Geel'),
        ('blauw', 'Blauw'),
    ], string='Papierkleur', default='geen', required=True)
    dik_papier = fields.Boolean(string='Dik papier', default=False)
    opmerking = fields.Char(string='Opmerking')

    student_count = fields.Integer(
        string='Aantal leerlingen',
        compute='_compute_student_count',
    )
    total_pages = fields.Integer(
        string="Totaal pagina's",
        compute='_compute_totals',
        store=True,
    )
    total_cost = fields.Monetary(
        string='Totale kost',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Valuta',
        default=lambda self: self.env.company.currency_id,
    )

    # --- Print options ---
    dubbelzijdig = fields.Boolean(string='Dubbelzijdig', default=True)
    nieten = fields.Boolean(string='Nieten', default=False)
    perforeren = fields.Boolean(string='Perforeren', default=False)
    gekleurd_papier = fields.Selection([
        ('gl4', 'Gekleurd papier optie 4'),
        ('gl5', 'Gekleurd papier optie 5'),
    ], string='Gekleurd papier')
    printer_code = fields.Char(
        string='Printercode',
        compute='_compute_printer_code',
        store=True,
    )

    state = fields.Selection([
        ('draft', 'Concept'),
        ('form_invullen', 'Formulier invullen'),
        ('afdrukken', 'Afdrukken'),
        ('doorrekenen', 'Doorrekenen'),
        ('done', 'Afgerond'),
    ], string='Status', default='draft', required=True, tracking=True)
    is_owner = fields.Boolean(compute='_compute_is_owner')

    @api.depends('dubbelzijdig', 'nieten', 'perforeren', 'gekleurd_papier')
    def _compute_printer_code(self):
        for record in self:
            codes = []
            if record.dubbelzijdig:
                codes.append('DZ')
            if record.nieten:
                codes.append('NT')
            if record.perforeren:
                codes.append('PF')
            if record.gekleurd_papier == 'gl4':
                codes.append('GL4')
            elif record.gekleurd_papier == 'gl5':
                codes.append('GL5')
            record.printer_code = '-'.join(codes) if codes else ''

    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = not record.create_uid or record.create_uid.id == self.env.uid

    @api.depends('school_id')
    def _compute_school_company_id(self):
        companies = self.env['res.company'].sudo().search([('school_id', '!=', False)])
        school_to_company = {c.school_id.id: c.id for c in companies}
        for record in self:
            record.school_company_id = school_to_company.get(record.school_id.id, False)

    @api.depends_context('uid', 'company')
    def _compute_allowed_school_json(self):
        schools = self.env.company.school_id or self.env.user.school_ids
        ids = schools.ids or self.env['myschool.org'].sudo().search([('org_type_id.name', '=', 'SCHOOL'), ('is_active', '=', True)]).ids
        for record in self:
            record.allowed_school_json = ids

    @api.depends('school_id')
    def _compute_available_klas_ids(self):
        OrgType = self.env['myschool.org.type']
        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        PropRel = self.env['myschool.proprelation']
        for record in self:
            if not record.school_id or not dept_type:
                record.available_klas_ids = False
                continue
            lln_rels = PropRel.search([
                ('id_org_parent', '=', record.school_id.id),
                ('id_org.org_type_id', '=', dept_type.id),
                ('id_org.name_short', '=', 'lln'),
            ])
            lln_ids = lln_rels.mapped('id_org').ids
            if not lln_ids:
                record.available_klas_ids = False
                continue
            klas_rels = PropRel.search([
                ('id_org_parent', 'in', lln_ids),
                ('id_org', '!=', False),
            ])
            record.available_klas_ids = klas_rels.mapped('id_org')

    @api.depends('kopie_leerkracht', 'student_ids')
    def _compute_aantal_kopies(self):
        for record in self:
            count = len(record.student_ids)
            if record.kopie_leerkracht:
                count += 1
            record.aantal_kopies = count

    @api.depends('student_ids')
    def _compute_student_count(self):
        for record in self:
            record.student_count = len(record.student_ids)

    def _get_students_from_classes(self):
        """Get all active students from the selected classes."""
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        if not person_tree_type or not self.klas_ids:
            return self.env['myschool.person']
        rels = PropRelation.search([
            ('proprelation_type_id', '=', person_tree_type.id),
            ('id_org', 'in', self.klas_ids.ids),
            ('id_person', '!=', False),
            ('is_active', '=', True),
        ])
        return rels.mapped('id_person')

    @api.onchange('klas_ids')
    def _onchange_klas_ids_select_students(self):
        """Select all students from the selected classes."""
        students = self._get_students_from_classes()
        self.student_ids = [(5, 0, 0)] + [(4, sid) for sid in students.ids]

    def action_select_all_students(self):
        """Select all students from the chosen classes."""
        for record in self:
            students = record._get_students_from_classes()
            record.student_ids = [(6, 0, students.ids)]

    def action_deselect_all_students(self):
        """Deselect all students."""
        for record in self:
            record.student_ids = [(5, 0, 0)]

    @api.depends('aantal_paginas', 'aantal_kopies', 'kleur', 'formaat', 'dik_papier')
    def _compute_totals(self):
        param = self.env['ir.config_parameter'].sudo()
        prijs_per_pagina = float(param.get_param('drukwerk.prijs_per_pagina', '0.03'))
        prijs_kleur = float(param.get_param('drukwerk.prijs_kleur', '0.05'))
        prijs_a3 = float(param.get_param('drukwerk.prijs_a3', '0.02'))
        prijs_dik = float(param.get_param('drukwerk.prijs_dik_papier', '0.04'))
        for record in self:
            pages = (record.aantal_paginas or 0) * (record.aantal_kopies or 0)
            price = prijs_per_pagina
            if record.kleur == 'kleur':
                price += prijs_kleur
            if record.formaat == 'a3':
                price += prijs_a3
            if record.dik_papier:
                price += prijs_dik
            record.total_pages = pages
            record.total_cost = pages * price

    @api.depends('name', 'titel')
    def _compute_display_name(self):
        for record in self:
            if record.titel:
                record.display_name = f'{record.name} - {record.titel}'
            else:
                record.display_name = record.name or ''

    _rec_names_search = ['name', 'titel']

    def action_open_config(self):
        config = self.env['drukwerk.config']._get_defaults()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Prijsinstellingen',
            'res_model': 'drukwerk.config',
            'view_mode': 'form',
            'res_id': config.id,
            'target': 'new',
        }

    @api.constrains('document_filename')
    def _check_pdf_only(self):
        for record in self:
            if record.document_filename and not record.document_filename.lower().endswith('.pdf'):
                raise ValidationError("Alleen PDF-bestanden zijn toegestaan. Upload een .pdf bestand.")

    @api.onchange('document_file', 'document_filename')
    def _onchange_document_file(self):
        if not self.document_file or not self.document_filename:
            return
        if not self.document_filename.lower().endswith('.pdf'):
            return
        try:
            pdf_data = base64.b64decode(self.document_file)
            page_count = self._count_pdf_pages(pdf_data)
            if page_count > 0:
                self.aantal_paginas = page_count
        except Exception:
            _logger.warning('Could not count pages for %s', self.document_filename, exc_info=True)

    @staticmethod
    def _count_pdf_pages(pdf_bytes):
        try:
            from PyPDF2 import PdfReader
            return len(PdfReader(io.BytesIO(pdf_bytes)).pages)
        except (ImportError, Exception):
            pass
        try:
            import pikepdf
            pdf = pikepdf.open(io.BytesIO(pdf_bytes))
            count = len(pdf.pages)
            pdf.close()
            return count
        except (ImportError, Exception):
            pass
        import re
        return len(re.findall(rb'/Type\s*/Page[^s]', pdf_bytes))

    @api.onchange('drukwerk_type')
    def _onchange_drukwerk_type(self):
        if self.drukwerk_type and self.state == 'draft':
            self.state = 'form_invullen'

    @api.onchange('school_id')
    def _onchange_school_id(self):
        self.klas_ids = [(5, 0, 0)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('drukwerk.record') or 'New'
            if vals.get('drukwerk_type') and (not vals.get('state') or vals.get('state') == 'draft'):
                vals['state'] = 'form_invullen'
        return super().create(vals_list)

    # --- Personeelslid actions ---

    def action_submit(self):
        for record in self:
            if record.state != 'form_invullen':
                raise UserError("Kan alleen vanuit de invulfase ingediend worden.")
            if not record.titel:
                raise UserError("Vul een omschrijving in.")
            if not record.klas_ids:
                raise UserError("Selecteer minstens één klas.")
            if not record.document_file:
                raise UserError("Upload een document.")
            record.state = 'afdrukken'
        self._notify_drukwerk_team()

    # --- Drukwerk actions ---

    def action_mark_printed(self):
        for record in self:
            if record.state != 'afdrukken':
                raise UserError("Kan alleen in de afdrukkenfase afgedrukt worden.")
            if record.drukwerk_type == 'examen':
                record.state = 'done'
            else:
                record.state = 'doorrekenen'
        gewoon_records = self.filtered(lambda r: r.drukwerk_type != 'examen')
        if gewoon_records:
            gewoon_records._notify_boekhouding()

    # --- Boekhouding actions ---

    def action_mark_invoiced(self):
        for record in self:
            if record.state != 'doorrekenen':
                raise UserError("Kan alleen in de doorrekeningsfase afgerond worden.")
            record.state = 'done'

    # --- Print actions ---

    def action_download_pdf(self):
        self.ensure_one()
        if not self.document_file:
            raise UserError("Geen document beschikbaar om af te drukken.")
        return {
            'type': 'ir.actions.act_url',
            'url': f'/drukwerk/print/{self.id}',
            'target': 'new',
        }

    # --- Shared actions ---

    def action_reset_to_form(self):
        for record in self:
            if record.state not in ('afdrukken',):
                raise UserError("Kan alleen vanuit de afdrukkenfase teruggezet worden.")
            record.state = 'form_invullen'

    def action_view_students(self):
        """Open wizard to select/deselect students."""
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        wiz = self.env['drukwerk.student.select.wizard'].create({
            'drukwerk_id': self.id,
        })
        lines = []
        if person_tree_type and self.klas_ids:
            rels = PropRelation.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('id_org', 'in', self.klas_ids.ids),
                ('id_person', '!=', False),
                ('is_active', '=', True),
            ])
            for rel in rels:
                lines.append({
                    'wizard_id': wiz.id,
                    'person_id': rel.id_person.id,
                    'klas_id': rel.id_org.id,
                    'selected': True,
                })
        if lines:
            self.env['drukwerk.student.select.line'].create(lines)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leerlingen selecteren',
            'res_model': 'drukwerk.student.select.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def unlink(self):
        if not self.env.user.has_group('drukwerk.group_drukwerk_admin'):
            for record in self:
                if record.state not in ('draft', 'form_invullen'):
                    raise UserError("U kunt alleen aanvragen verwijderen die nog niet ingediend zijn.")
        return super().unlink()

    def _notify_drukwerk_team(self):
        drukwerk_group = self.env.ref(
            'drukwerk.group_drukwerk_drukwerk', raise_if_not_found=False)
        if not drukwerk_group:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in drukwerk_group.user_ids:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Drukwerk afdrukken',
                    note=f'Drukwerk aanvraag "{record.titel}" is klaar om af te drukken.',
                    user_id=user.id,
                )

    def _notify_boekhouding(self):
        boekhouding_group = self.env.ref(
            'drukwerk.group_drukwerk_boekhouding', raise_if_not_found=False)
        if not boekhouding_group:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in boekhouding_group.user_ids:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Drukwerk doorrekenen',
                    note=f'Drukwerk "{record.titel}" is afgedrukt en kan doorgerekend worden.',
                    user_id=user.id,
                )

    @api.model
    def _cron_print_deadline_reminder(self):
        """Send reminder activities for records with print deadline tomorrow."""
        tomorrow = fields.Date.today() + timedelta(days=1)
        records = self.search([
            ('print_deadline', '=', tomorrow),
            ('state', '=', 'afdrukken'),
        ])
        if not records:
            return
        drukwerk_group = self.env.ref(
            'drukwerk.group_drukwerk_drukwerk', raise_if_not_found=False)
        admin_group = self.env.ref(
            'drukwerk.group_drukwerk_admin', raise_if_not_found=False)
        users = self.env['res.users']
        if drukwerk_group:
            users |= drukwerk_group.user_ids
        if admin_group:
            users |= admin_group.user_ids
        if not users:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in records:
            for user in users:
                existing = self.env['mail.activity'].search([
                    ('res_model', '=', 'drukwerk.record'),
                    ('res_id', '=', record.id),
                    ('user_id', '=', user.id),
                    ('summary', '=', 'Drukwerk deadline morgen'),
                ], limit=1)
                if existing:
                    continue
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Drukwerk deadline morgen',
                    note=f'Drukwerk "{record.titel}" moet morgen ({tomorrow}) afgedrukt zijn!',
                    user_id=user.id,
                    date_deadline=tomorrow,
                )
