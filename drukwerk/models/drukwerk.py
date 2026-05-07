import base64
import io
import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DrukwerkRecord(models.Model):
    _name = 'drukwerk.record'
    _description = 'Drukwerk Aanvraag'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'myschool.allowed.schools.mixin']
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
    examen_variant = fields.Selection([
        ('wit', 'Wit — geen hulpmiddelen'),
        ('groen', 'Groen — met hulpmiddelen'),
        ('geel', 'Geel — vergrote tekst / specifieke hulpmiddelen'),
    ], string='Examen-versie',
       help='Kleurcode van het examenpapier afhankelijk van het toegestane '
            'gebruik van hulpmiddelen. Wit = geen hulpmiddelen, '
            'Groen = met hulpmiddelen, Geel = vergrote tekst of specifieke '
            'aanpassingen voor leerlingen met bv. dyslexie.')
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
    kopie_leerkracht = fields.Boolean(
        string='Kopie leerkracht',
        default=False,
        help='Aanvinken voor 1 extra exemplaar voor de leerkracht zelf '
             '(bovenop het totaal voor de leerlingen).',
    )
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
    cost_per_student = fields.Monetary(
        string='Kost per leerling',
        currency_field='currency_id',
        compute='_compute_cost_per_student',
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
    liggend = fields.Boolean(string='Liggend', default=False)
    sorteren = fields.Boolean(string='Sorteren', default=False)
    a3_plooien = fields.Boolean(string='A3 plooien', default=False)
    boekje_a4 = fields.Boolean(string='Boekje A4', default=False)
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
        ('form_invullen', 'Concept'),
        ('afdrukken', 'Af te drukken'),
        ('done', 'Afgedrukt'),
        ('gestockeerd', 'Gestockeerd'),
    ], string='Status', default='draft', required=True, tracking=True)
    done_date = fields.Datetime(
        string='Datum afgerond',
        readonly=True,
        help='Tijdstip waarop de aanvraag de status Afgerond bereikte. '
             'Wordt gebruikt om automatisch te stockeren na X dagen.',
    )
    is_owner = fields.Boolean(compute='_compute_is_owner')
    can_edit_content = fields.Boolean(
        compute='_compute_can_edit_content',
        help='True wanneer de inhoud van de aanvraag aangepast mag worden: '
             'in concept- of formulier-fase, of in de afdrukken-fase voor de eigenaar.',
    )
    can_select_color = fields.Boolean(compute='_compute_can_select_color')
    is_drukwerk_team = fields.Boolean(
        compute='_compute_is_drukwerk_team',
        help='True voor gebruikers in de drukkerij- of admin-groep — gebruikt '
             'om dubbele Verwijderen-knoppen te vermijden voor users die zowel '
             'personeelslid als drukker/admin zijn.',
    )

    @api.depends_context('uid')
    def _compute_is_drukwerk_team(self):
        in_team = (
            self.env.user.has_group('drukwerk.group_drukwerk_drukwerk')
            or self.env.user.has_group('drukwerk.group_drukwerk_admin')
        )
        for record in self:
            record.is_drukwerk_team = in_team

    @api.depends('state', 'is_owner', 'is_drukwerk_team')
    def _compute_can_edit_content(self):
        for record in self:
            record.can_edit_content = (
                record.state in ('draft', 'form_invullen')
                or (record.state == 'afdrukken' and record.is_owner)
                # Drukkerij-team / admin moet ook na indienen kleine
                # correcties kunnen doen (typo's, papierkleur, ...).
                or (record.state == 'afdrukken' and record.is_drukwerk_team)
            )

    @api.depends_context('uid')
    def _compute_can_select_color(self):
        allowed = (
            self.env.user.has_group('drukwerk.group_drukwerk_personeelslid_kleur')
            or self.env.user.has_group('drukwerk.group_drukwerk_admin')
        )
        for record in self:
            record.can_select_color = allowed

    @api.constrains('kleur')
    def _check_kleur_permission(self):
        for record in self:
            if record.kleur == 'kleur' and not record.can_select_color:
                raise ValidationError(
                    "U heeft geen rechten om kleur-drukwerk aan te vragen. "
                    "Vraag een collega met de rol 'Personeelslid Kleur' om de aanvraag in te dienen."
                )

    @api.depends('dubbelzijdig', 'nieten', 'perforeren', 'liggend',
                 'sorteren', 'a3_plooien', 'boekje_a4',
                 'gekleurd_papier', 'papier_kleur',
                 'drukwerk_type', 'examen_variant')
    def _compute_printer_code(self):
        for record in self:
            codes = []
            if record.drukwerk_type == 'examen' and record.examen_variant:
                codes.append(f'EXAMEN-{record.examen_variant.upper()}')
            if record.dubbelzijdig:
                codes.append('R/V')
            if record.nieten:
                codes.append('NIET')
            if record.perforeren:
                codes.append('PERFO')
            if record.liggend:
                codes.append('LIGGEND')
            if record.sorteren:
                codes.append('SORTEREN')
            if record.a3_plooien:
                codes.append('A3 plooien')
            if record.boekje_a4:
                codes.append('BoekjeA4')
            if record.papier_kleur != 'geen':
                if record.gekleurd_papier == 'gl4':
                    codes.append('Lade4 kleur 1')
                elif record.gekleurd_papier == 'gl5':
                    codes.append('Lade5 kleur 2')
            record.printer_code = '-'.join(codes) if codes else ''

    @api.onchange('papier_kleur')
    def _onchange_papier_kleur(self):
        if self.papier_kleur == 'geen':
            self.gekleurd_papier = False

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

    @api.depends('school_id')
    @api.depends_context('uid')
    def _compute_available_klas_ids(self):
        OrgType = self.env['myschool.org.type']
        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        PropRel = self.env['myschool.proprelation']
        # Bepaal eenmalig de teaching-klassen voor de huidige gebruiker (indien leerkracht)
        teacher_klas_ids = None
        if 'lessenrooster.line' in self.env:
            Person = self.env['myschool.person']
            person = Person.sudo().search([('odoo_user_id', '=', self.env.uid)], limit=1)
            if person:
                lines = self.env['lessenrooster.line'].sudo().search([
                    ('leerkracht_id', '=', person.id),
                ])
                teacher_klas_ids = set(lines.mapped('klas_id').ids)
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
            klassen = klas_rels.mapped('id_org')
            # Als de gebruiker een leerkracht is met lessen, filter op zijn klassen
            if teacher_klas_ids:
                klassen = klassen.filtered(lambda k: k.id in teacher_klas_ids)
            record.available_klas_ids = klassen

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
        if not self.klas_ids:
            return self.env['myschool.person']
        return self.env['myschool.person'].sudo().search([
            ('tree_org_id', 'in', self.klas_ids.ids),
            ('is_active', '=', True),
        ])

    @api.onchange('klas_ids')
    def _onchange_klas_ids_select_students(self):
        """Select all students from the selected classes."""
        students = self._get_students_from_classes()
        self.student_ids = [(5, 0, 0)] + [(4, sid) for sid in students.ids]

    def action_select_all_students(self):
        """Select all students from the chosen classes."""
        for record in self:
            if record.state == 'done':
                raise UserError("De leerlingenselectie kan niet meer gewijzigd worden voor een afgeronde aanvraag.")
            students = record._get_students_from_classes()
            record.student_ids = [(6, 0, students.ids)]

    def action_deselect_all_students(self):
        """Deselect all students."""
        for record in self:
            if record.state == 'done':
                raise UserError("De leerlingenselectie kan niet meer gewijzigd worden voor een afgeronde aanvraag.")
            record.student_ids = [(5, 0, 0)]

    @api.depends('aantal_paginas', 'aantal_kopies', 'student_ids',
                 'kleur', 'formaat', 'dik_papier')
    def _compute_totals(self):
        param = self.env['ir.config_parameter'].sudo()
        prijs_per_pagina = float(param.get_param('drukwerk.prijs_per_pagina', '0.03'))
        prijs_kleur = float(param.get_param('drukwerk.prijs_kleur', '0.05'))
        prijs_a3 = float(param.get_param('drukwerk.prijs_a3', '0.02'))
        prijs_dik = float(param.get_param('drukwerk.prijs_dik_papier', '0.04'))
        for record in self:
            student_count = len(record.student_ids)
            pages = (record.aantal_paginas or 0) * (record.aantal_kopies or 0)
            page_price = prijs_per_pagina
            if record.kleur == 'kleur':
                page_price += prijs_kleur
            if record.formaat == 'a3':
                page_price += prijs_a3
            if record.dik_papier:
                page_price += prijs_dik
            billable_pages = (record.aantal_paginas or 0) * student_count
            record.total_pages = pages
            record.total_cost = billable_pages * page_price

    @api.depends('total_cost', 'student_ids')
    def _compute_cost_per_student(self):
        for record in self:
            student_count = len(record.student_ids)
            record.cost_per_student = (record.total_cost / student_count) if student_count else 0.0

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

    def action_open_class_report(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Drukwerk per klas',
            'res_model': 'drukwerk.class.report',
            'view_mode': 'list',
            'context': {'search_default_type_gewoon': 1},
            'target': 'current',
        }

    def action_open_student_report(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Drukwerk per leerling',
            'res_model': 'drukwerk.student.report',
            'view_mode': 'list',
            'context': {'search_default_type_gewoon': 1},
            'target': 'current',
        }

    @api.constrains('document_filename')
    def _check_pdf_only(self):
        for record in self:
            if record.document_filename and not record.document_filename.lower().endswith('.pdf'):
                raise ValidationError("Alleen PDF-bestanden zijn toegestaan. Upload een .pdf bestand.")

    def _recount_pages(self):
        """Update aantal_paginas and liggend by reading the PDF from document_file."""
        for record in self:
            if not record.document_file:
                continue
            try:
                pdf_data = base64.b64decode(record.document_file)
                page_count = self._count_pdf_pages(pdf_data)
                if page_count > 0:
                    record.aantal_paginas = page_count
                record.liggend = self._is_pdf_landscape(pdf_data)
            except Exception:
                _logger.warning('Could not read PDF info for %s', record.document_filename, exc_info=True)

    @api.onchange('document_file', 'document_filename')
    def _onchange_document_file(self):
        if self.document_file and self.document_filename and self.document_filename.lower().endswith('.pdf'):
            self._recount_pages()

    @staticmethod
    def _is_pdf_landscape(pdf_bytes):
        """Return True if the first page of the PDF is landscape (width > height)."""
        try:
            from PyPDF2 import PdfReader
            page = PdfReader(io.BytesIO(pdf_bytes)).pages[0]
            mb = page.mediabox
            return float(mb.width) > float(mb.height)
        except (ImportError, Exception):
            pass
        try:
            import pikepdf
            pdf = pikepdf.open(io.BytesIO(pdf_bytes))
            mb = pdf.pages[0].MediaBox
            width = float(mb[2]) - float(mb[0])
            height = float(mb[3]) - float(mb[1])
            pdf.close()
            return width > height
        except (ImportError, Exception):
            pass
        return False

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
            if vals.get('name', 'New') == 'New' or not vals.get('name'):
                vals['name'] = self._next_reference()
            if vals.get('drukwerk_type') and (not vals.get('state') or vals.get('state') == 'draft'):
                vals['state'] = 'form_invullen'
        records = super().create(vals_list)
        for record in records:
            if not record.name or record.name == 'New':
                record.sudo().name = self._next_reference()
        records.filtered(lambda r: r.document_file)._recount_pages()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'document_file' in vals:
            self._recount_pages()
        return res

    def _next_reference(self):
        """Get next unique reference, syncing the sequence if needed."""
        last_record = self.sudo().search(
            [('name', 'like', 'DWK-')],
            order='name desc', limit=1,
        )
        last_number = 0
        if last_record:
            try:
                last_number = int(last_record.name.replace('DWK-', ''))
            except ValueError:
                pass
        seq = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'drukwerk.record'),
        ], limit=1)
        if not seq:
            seq = self.env['ir.sequence'].sudo().create({
                'name': 'Drukwerk Aanvraag',
                'code': 'drukwerk.record',
                'prefix': 'DWK-',
                'padding': 4,
                'number_next': last_number + 1,
                'number_increment': 1,
                'company_id': False,
            })
            _logger.info('[DWK] Auto-created ir.sequence for drukwerk.record')
        if seq.number_next <= last_number:
            seq.sudo().write({'number_next': last_number + 1})
        ref = seq.sudo()._next()
        _logger.info('[DWK] Generated reference: %s', ref)
        return ref

    # --- Personeelslid actions ---

    def action_submit(self):
        for record in self:
            if record.state != 'form_invullen':
                raise UserError("Kan alleen vanuit de invulfase ingediend worden.")
            if not record.titel:
                raise UserError("Vul een omschrijving in.")
            if not record.print_deadline:
                raise UserError("Vul de gewenste afdrukdatum in.")
            if not record.klas_ids and not record.kopie_leerkracht:
                raise UserError(
                    "Selecteer minstens één klas, of vink "
                    "'Kopie leerkracht' aan om enkel voor jezelf af te drukken."
                )
            if not record.document_file:
                raise UserError("Upload een document.")
            record.state = 'afdrukken'
        self._notify_drukwerk_team()

    def action_open_details(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Extra info',
            'res_model': 'drukwerk.record',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('drukwerk.view_drukwerk_form_details').id, 'form')],
            'target': 'new',
        }

    def action_submit_from_dialog(self):
        self.ensure_one()
        self.action_submit()
        # Sluit de dialog en navigeer naar de drukwerk-lijst zodat de leerkracht
        # de nieuwe aanvraag in het overzicht ziet i.p.v. te blijven hangen op de form.
        action = self.env.ref('drukwerk.action_drukwerk').sudo().read()[0]
        action['target'] = 'main'
        return action

    # --- Drukwerk actions ---

    def action_mark_printed(self):
        for record in self:
            if record.state != 'afdrukken':
                raise UserError("Kan alleen in de afdrukkenfase afgedrukt worden.")
            record.state = 'done'
            record.done_date = fields.Datetime.now()
        self._send_notification('done')

    def action_stockeren(self):
        """Move done records into stock (gestockeerd)."""
        for record in self:
            if record.state != 'done':
                raise UserError(
                    "Alleen afgeronde aanvragen kunnen gestockeerd worden."
                )
            record.state = 'gestockeerd'

    @api.model
    def _cron_auto_stock(self):
        """Automatically move records from 'done' to 'gestockeerd' once their
        done_date is older than the configured threshold (default 30 days)."""
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'drukwerk.auto_stock_after_days', '30'))
        cutoff = fields.Datetime.now() - timedelta(days=days)
        records = self.search([
            ('state', '=', 'done'),
            ('done_date', '!=', False),
            ('done_date', '<', cutoff),
        ])
        if records:
            records.write({'state': 'gestockeerd'})
            _logger.info(
                "Drukwerk auto-stock: %d records moved to gestockeerd "
                "(threshold %d days).", len(records), days)

    # --- Print actions ---

    def action_download_pdf(self):
        self.ensure_one()
        if not self.document_file:
            raise UserError("Geen document beschikbaar om af te drukken.")
        return {
            'type': 'ir.actions.client',
            'tag': 'drukwerk_print_and_confirm',
            'params': {
                'record_id': self.id,
                'url': f'/drukwerk/print/{self.id}',
            },
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
        wiz = self.env['drukwerk.student.select.wizard'].create({
            'drukwerk_id': self.id,
            'readonly_mode': self.state == 'done',
        })
        lines = []
        if self.klas_ids:
            students = self.env['myschool.person'].sudo().search([
                ('tree_org_id', 'in', self.klas_ids.ids),
                ('is_active', '=', True),
            ])
            for student in students:
                lines.append({
                    'wizard_id': wiz.id,
                    'person_id': student.id,
                    'klas_id': student.tree_org_id.id,
                    'selected': student.id in self.student_ids.ids,
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

    def action_open_extra_klas_wizard(self):
        """Open wizard om klassen toe te voegen die niet door de leerkracht worden lesgegeven."""
        self.ensure_one()
        wiz = self.env['drukwerk.extra.klas.wizard'].create({
            'drukwerk_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Andere klas toevoegen',
            'res_model': 'drukwerk.extra.klas.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_delete(self):
        self.unlink()
        # Generieke client-action die terugkeert naar de vorige controller
        # zodat filters/sortering/scroll behouden blijven (zie myschool_core).
        return {
            'type': 'ir.actions.client',
            'tag': 'myschool_back_to_previous',
            'params': {
                'fallback_action': 'drukwerk.action_drukwerk',
            },
        }

    def unlink(self):
        privileged = (
            self.env.user.has_group('drukwerk.group_drukwerk_admin')
            or self.env.user.has_group('drukwerk.group_drukwerk_drukwerk')
        )
        if not privileged:
            for record in self:
                if record.state not in ('draft', 'form_invullen'):
                    raise UserError("U kunt alleen aanvragen verwijderen die nog niet ingediend zijn.")
        return super().unlink()

    def _notify_drukwerk_team(self):
        """Stuur een mail.activity (todo) én een email naar elke gebruiker
        in de drukkerij-rol zodra er nieuw drukwerk klaarstaat."""
        drukwerk_group = self.env.ref(
            'drukwerk.group_drukwerk_drukwerk', raise_if_not_found=False)
        if not drukwerk_group:
            return
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False)
        new_template = self.env.ref(
            'drukwerk.email_template_drukwerk_new', raise_if_not_found=False)
        partner_ids = drukwerk_group.user_ids.partner_id.ids

        for record in self:
            # Activity (todo) per drukker
            for user in drukwerk_group.user_ids:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Drukwerk afdrukken',
                    note=f'Drukwerk aanvraag "{record.titel}" is klaar om af te drukken.',
                    user_id=user.id,
                )
            # Email naar alle drukkers tegelijk via mail-template
            if new_template and partner_ids:
                new_template.send_mail(
                    record.id,
                    force_send=False,  # respecteer de mail-queue
                    email_values={'partner_ids': [(6, 0, partner_ids)]},
                )

    _NOTIFICATION_TEMPLATES = {
        'done': 'drukwerk.email_template_drukwerk_done',
    }

    def _send_notification(self, notification_type):
        template_xmlid = self._NOTIFICATION_TEMPLATES.get(notification_type)
        if not template_xmlid:
            return
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            return
        for record in self:
            rendered = template._render_template(
                template.body_html, template.render_model, [record.id],
                engine='inline_template',
                options={'post_process': True},
            )
            body = rendered.get(record.id, '')
            if body:
                record.message_post(body=Markup(body), subtype_xmlid='mail.mt_note')

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
