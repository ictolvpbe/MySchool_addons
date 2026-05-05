import logging

from markupsafe import Markup

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class Activiteiten(models.Model):
    _name = 'activiteiten.record'
    _description = 'Activiteiten'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'myschool.allowed.schools.mixin']

    name = fields.Char(
        string='Referentie',
        copy=False,
        readonly=True,
        default='New',
    )
    titel = fields.Char(string='Titel activiteit')
    description = fields.Text(string='Beschrijving')
    activity_type = fields.Selection([
        ('binnenschools', 'Binnenschoolse activiteit'),
        ('buitenschools', 'Buitenschoolse activiteit'),
    ], string='Type activiteit', tracking=True)
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
    datetime = fields.Datetime(string='Startdatum en tijdstip')
    datetime_end = fields.Datetime(string='Einddatum en tijdstip')
    available_klas_ids = fields.Many2many(
        'myschool.org',
        compute='_compute_available_klas_ids',
        store=False,
    )
    klas_ids = fields.Many2many(
        'myschool.org',
        'activiteiten_record_klas_rel',
        'record_id', 'org_id',
        string='Klassen',
        domain="[('id', 'in', available_klas_ids)]",
    )
    available_leerkracht_ids = fields.Many2many(
        'myschool.person',
        compute='_compute_available_leerkracht_ids',
        store=False,
    )
    leerkracht_ids = fields.Many2many(
        'myschool.person',
        'activiteiten_record_leerkracht_rel',
        'record_id', 'person_id',
        string='Leerkrachten',
        domain="[('id', 'in', available_leerkracht_ids)]",
    )
    leerkracht_count = fields.Integer(
        string='Aantal leerkrachten',
        compute='_compute_leerkracht_count',
    )
    price = fields.Monetary(string='Geschatte kost', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency',
        string='Valuta',
        default=lambda self: self.env.company.currency_id,
    )
    lokaal = fields.Char(string='Lokaal')
    locatie = fields.Char(string='Locatie')
    locatie_adres = fields.Char(string='Adres')
    is_active = fields.Boolean(string='Actief', default=True)
    state = fields.Selection([
        ('draft', 'Concept'),
        ('form_invullen', 'Concept'),
        ('bus_check', 'Bus controle'),
        ('bus_refused', 'Bus geweigerd'),
        ('pending_approval', 'Wacht op goedkeuring'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('s_code', 'S-Code controle'),
        ('vervanging', 'Vervanging inplannen'),
        ('done', 'Afgerond'),
    ], string='Status', default='draft', required=True, tracking=True)

    vervoer_type = fields.Selection([
        ('bus', 'Schoolbus'),
        ('openbaar_vervoer', 'Openbaar vervoer'),
        ('te_voet', 'Te voet'),
        ('fiets', 'Fiets'),
        ('auto', 'Met de wagen'),
        ('anders', 'Anders'),
    ], string='Vervoer', default='bus',
       help='Hoe verplaatst de groep zich tijdens deze activiteit. '
            'Selectie van "Schoolbus" triggert de bus-controle-flow.')
    bus_nodig = fields.Boolean(string='Bus nodig', default=False)

    @api.onchange('vervoer_type')
    def _onchange_vervoer_type(self):
        for record in self:
            record.bus_nodig = (record.vervoer_type == 'bus')
    bus_price = fields.Monetary(
        string='Prijs van bus',
        currency_field='currency_id',
    )
    bus_available = fields.Boolean(string='Bus beschikbaar')
    aantal_bussen = fields.Selection([
        ('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'),
        ('6', '6'), ('7', '7'), ('8', '8'), ('9', '9'), ('10', '10'),
    ], string='Aantal bussen', default='1')
    bus_ids = fields.One2many(
        'activiteiten.bus', 'activiteit_id', string='Busverdeling',
    )
    document_ids = fields.Many2many(
        'ir.attachment', string='Documenten',
    )
    s_code_name = fields.Char(string='S-Code')
    s_code_price = fields.Monetary(
        string='S-Code bedrag',
        currency_field='currency_id',
    )
    kosten_ids = fields.One2many(
        'activiteiten.kosten.line', 'activiteit_id',
        string='Kosten',
    )
    kosten_vast_ids = fields.One2many(
        'activiteiten.kosten.line', 'activiteit_id',
        string='Vaste kosten',
        domain=[('kosten_type', '=', 'vast')],
    )
    kosten_variabel_ids = fields.One2many(
        'activiteiten.kosten.line', 'activiteit_id',
        string='Variabele kosten',
        domain=[('kosten_type', '=', 'variabel')],
    )
    totale_kost = fields.Monetary(
        string='Totale kost',
        currency_field='currency_id',
        compute='_compute_totale_kost',
        store=True,
    )
    kosten_display = fields.Html(
        string='Kosten overzicht',
        compute='_compute_kosten_display',
        sanitize=False,
    )
    bijdragen_regeling = fields.Boolean(
        string='Bijdragen regeling',
        default=False,
        help='Geeft aan dat deze activiteit onder de bijdragenregeling valt.',
    )
    verzekering_done = fields.Boolean(string='Verzekering geregeld', default=False)
    wizard_step = fields.Selection([
        ('1', 'Begeleiders'),
        ('2', 'Opmerkingen'),
        ('3', 'Kosten'),
        ('4', 'Documenten'),
    ], default='1', copy=False)
    rejection_reason = fields.Text(string='Reden voor afkeuring')
    invite_ids = fields.One2many(
        'activiteiten.invite', 'activiteit_id', string='Uitnodigingen',
    )
    student_count = fields.Integer(
        string='Aantal leerlingen',
        compute='_compute_student_count',
    )
    snapshot_line_ids = fields.One2many(
        'activiteiten.snapshot.line', 'activiteit_id',
        string='Deelnemers snapshot',
    )
    snapshot_student_count = fields.Integer(
        string='Leerlingen (ingediend)',
        compute='_compute_snapshot_counts',
    )
    snapshot_leerkracht_count = fields.Integer(
        string='Leerkrachten (ingediend)',
        compute='_compute_snapshot_counts',
    )
    is_owner = fields.Boolean(compute='_compute_is_owner')
    can_edit_s_code = fields.Boolean(
        compute='_compute_can_edit_s_code',
        help='True wanneer de huidige gebruiker de S-Code mag bewerken: '
             'enkel boekhouding/admin in de status S-Code controle.',
    )

    @api.depends_context('uid')
    @api.depends('state')
    def _compute_can_edit_s_code(self):
        is_boekhouding_or_admin = (
            self.env.user.has_group('activiteiten.group_activiteiten_boekhouding')
            or self.env.user.has_group('activiteiten.group_activiteiten_admin')
        )
        for record in self:
            record.can_edit_s_code = (
                is_boekhouding_or_admin and record.state == 's_code'
            )
    can_manage_invites = fields.Boolean(compute='_compute_can_manage_invites')
    display_state = fields.Selection([
        ('draft', 'Concept'),
        ('form_invullen', 'Formulier invullen'),
        ('bus_check', 'Controle bus'),
        ('bus_refused', 'Bus geweigerd'),
        ('pending_approval', 'Wacht op goedkeuring'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('done', 'Afgerond'),
    ], string='Status', compute='_compute_display_state')

    @api.depends('school_id')
    def _compute_school_company_id(self):
        companies = self.env['res.company'].sudo().search([('school_id', '!=', False)])
        school_to_company = {c.school_id.id: c.id for c in companies}
        for record in self:
            record.school_company_id = school_to_company.get(record.school_id.id, False)

    @api.depends('state')
    @api.depends_context('uid')
    def _compute_display_state(self):
        is_manager = self.env.user.has_group('activiteiten.group_activiteiten_directie') or \
                     self.env.user.has_group('activiteiten.group_activiteiten_admin') or \
                     self.env.user.has_group('activiteiten.group_activiteiten_boekhouding') or \
                     self.env.user.has_group('activiteiten.group_activiteiten_vervangingen') or \
                     self.env.user.has_group('activiteiten.group_activiteiten_aankoop')
        for record in self:
            if not is_manager and record.state in ('s_code', 'vervanging'):
                record.display_state = 'approved'
            else:
                record.display_state = record.state

    @api.depends('klas_ids')
    def _compute_student_count(self):
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        for record in self:
            if person_tree_type and record.klas_ids:
                record.student_count = PropRelation.search_count([
                    ('proprelation_type_id', '=', person_tree_type.id),
                    ('id_org', 'in', record.klas_ids.ids),
                    ('id_person', '!=', False),
                    ('is_active', '=', True),
                ])
            else:
                record.student_count = 0

    @api.depends('snapshot_line_ids')
    def _compute_snapshot_counts(self):
        for record in self:
            lines = record.snapshot_line_ids.filtered(lambda l: not l.date_to)
            record.snapshot_student_count = len(
                lines.filtered(lambda l: l.snapshot_type == 'student'))
            record.snapshot_leerkracht_count = len(
                lines.filtered(lambda l: l.snapshot_type == 'leerkracht'))

    def _get_current_students(self):
        """Get the current student person records for the selected classes."""
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

    def _create_snapshot(self):
        """Create snapshot lines for current students and teachers."""
        SnapshotLine = self.env['activiteiten.snapshot.line']
        today = fields.Date.context_today(self)
        for record in self:
            # Remove old snapshot lines (fresh snapshot on each submit)
            record.snapshot_line_ids.sudo().unlink()
            vals_list = []
            # Students
            students = record._get_current_students()
            for student in students:
                vals_list.append({
                    'activiteit_id': record.id,
                    'person_id': student.id,
                    'snapshot_type': 'student',
                    'date_from': today,
                })
            # Teachers
            for teacher in record.leerkracht_ids:
                vals_list.append({
                    'activiteit_id': record.id,
                    'person_id': teacher.id,
                    'snapshot_type': 'leerkracht',
                    'date_from': today,
                })
            if vals_list:
                SnapshotLine.create(vals_list)

    def action_update_snapshot(self):
        """Update snapshot: mark people no longer in the class/activity."""
        today = fields.Date.context_today(self)
        for record in self:
            current_students = record._get_current_students()
            current_teachers = record.leerkracht_ids
            for line in record.snapshot_line_ids.filtered(lambda l: not l.date_to):
                if line.snapshot_type == 'student' and line.person_id not in current_students:
                    line.date_to = today
                elif line.snapshot_type == 'leerkracht' and line.person_id not in current_teachers:
                    line.date_to = today
            # Add new people that weren't in the snapshot yet
            existing_student_ids = record.snapshot_line_ids.filtered(
                lambda l: l.snapshot_type == 'student' and not l.date_to
            ).mapped('person_id').ids
            existing_teacher_ids = record.snapshot_line_ids.filtered(
                lambda l: l.snapshot_type == 'leerkracht' and not l.date_to
            ).mapped('person_id').ids
            vals_list = []
            for student in current_students:
                if student.id not in existing_student_ids:
                    vals_list.append({
                        'activiteit_id': record.id,
                        'person_id': student.id,
                        'snapshot_type': 'student',
                        'date_from': today,
                    })
            for teacher in current_teachers:
                if teacher.id not in existing_teacher_ids:
                    vals_list.append({
                        'activiteit_id': record.id,
                        'person_id': teacher.id,
                        'snapshot_type': 'leerkracht',
                        'date_from': today,
                    })
            if vals_list:
                self.env['activiteiten.snapshot.line'].create(vals_list)

    def _open_snapshot_wizard(self, snapshot_type):
        """Open the snapshot wizard for the given type."""
        self.ensure_one()
        # Auto-update snapshot when opening
        if self.state not in ('draft', 'form_invullen'):
            self.action_update_snapshot()
        wiz = self.env['activiteiten.snapshot.wizard'].create({
            'activiteit_id': self.id,
            'snapshot_type': snapshot_type,
        })
        label = 'Leerlingen' if snapshot_type == 'student' else 'Leerkrachten'
        return {
            'type': 'ir.actions.act_window',
            'name': label,
            'res_model': 'activiteiten.snapshot.wizard',
            'view_mode': 'form',
            'res_id': wiz.id,
            'target': 'new',
        }

    def action_open_snapshot_students(self):
        return self._open_snapshot_wizard('student')

    def action_open_snapshot_leerkrachten(self):
        return self._open_snapshot_wizard('leerkracht')

    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = not record.create_uid or record.create_uid.id == self.env.uid

    @api.depends_context('uid')
    def _compute_can_manage_invites(self):
        is_admin = self.env.user.has_group('activiteiten.group_activiteiten_admin')
        for record in self:
            record.can_manage_invites = is_admin or record.is_owner


    dates_display = fields.Html(
        string='Datum',
        compute='_compute_dates_display',
        sanitize=False,
    )

    @api.depends('datetime', 'datetime_end')
    def _compute_dates_display(self):
        wrap = '<span style="display:inline-flex;flex-wrap:wrap;gap:2px 4px;align-items:center">%s</span>'
        for record in self:
            if record.datetime and record.datetime_end:
                start = fields.Datetime.context_timestamp(record, record.datetime)
                end = fields.Datetime.context_timestamp(record, record.datetime_end)
                if start.date() == end.date():
                    parts = (
                        '<span>%s</span>'
                        '<span>%s</span>'
                        '<span>→</span>'
                        '<span>%s</span>'
                    ) % (
                        start.strftime('%d %b %Y'),
                        start.strftime('%H:%M'),
                        end.strftime('%H:%M'),
                    )
                else:
                    parts = (
                        '<span>%s</span>'
                        '<span>→</span>'
                        '<span>%s</span>'
                    ) % (
                        start.strftime('%d %b %Y %H:%M'),
                        end.strftime('%d %b %Y %H:%M'),
                    )
                record.dates_display = wrap % parts
            elif record.datetime:
                dt = fields.Datetime.context_timestamp(record, record.datetime)
                record.dates_display = wrap % ('<span>%s</span>' % dt.strftime('%d %b %Y %H:%M'))
            else:
                record.dates_display = ''

    def _get_verzekering_pct(self):
        """Get the insurance percentage from settings (default 2%)."""
        pct = self.env['ir.config_parameter'].sudo().get_param(
            'activiteiten.verzekering_pct', '2.0')
        try:
            return float(pct)
        except (ValueError, TypeError):
            return 2.0

    def _get_details_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Extra info',
            'res_model': 'activiteiten.record',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('activiteiten.view_activiteiten_form_details').id, 'form')],
            'target': 'new',
        }

    def action_open_details(self):
        self.ensure_one()
        self.wizard_step = '1'
        return self._get_details_action()

    def action_wizard_next(self):
        self.ensure_one()
        next_step = {'1': '2', '2': '3', '3': '4'}.get(self.wizard_step)
        if next_step:
            self.wizard_step = next_step
        return self._get_details_action()

    def action_wizard_prev(self):
        self.ensure_one()
        prev_step = {'2': '1', '3': '2', '4': '3'}.get(self.wizard_step)
        if prev_step:
            self.wizard_step = prev_step
        return self._get_details_action()

    def action_submit_from_dialog(self):
        self.ensure_one()
        self.action_submit_form()
        return {'type': 'ir.actions.act_window_close'}

    @api.depends('kosten_ids.bedrag')
    def _compute_totale_kost(self):
        for record in self:
            record.totale_kost = sum(record.kosten_ids.mapped('bedrag'))

    @api.onchange('bus_price', 'kosten_ids')
    def _onchange_recalculate_verzekering(self):
        pct = self._get_verzekering_pct() / 100.0
        verzekering_line = None
        other_total = 0
        for line in self.kosten_ids:
            if line.is_auto and 'Verzekering' in (line.omschrijving or ''):
                verzekering_line = line
            elif line.is_auto and line.omschrijving == 'Bus' and self.bus_price:
                line.bedrag = self.bus_price
                other_total += line.bedrag or 0
            else:
                other_total += line.bedrag or 0
        if verzekering_line:
            verzekering_line.bedrag = other_total * pct

    @api.depends('kosten_ids.bedrag', 'kosten_ids.omschrijving')
    def _compute_kosten_display(self):
        for record in self:
            lines = []
            for line in record.kosten_ids:
                lines.append('%s: € %.2f' % (line.omschrijving or '', line.bedrag or 0))
            record.kosten_display = '<br/>'.join(lines) if lines else ''

    @api.depends('school_id')
    def _compute_available_klas_ids(self):
        OrgType = self.env['myschool.org.type']
        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        PropRel = self.env['myschool.proprelation']
        for record in self:
            if not record.school_id or not dept_type:
                record.available_klas_ids = False
                continue
            # Find lln departments under the school
            lln_rels = PropRel.search([
                ('id_org_parent', '=', record.school_id.id),
                ('id_org.org_type_id', '=', dept_type.id),
                ('id_org.name_short', '=', 'lln'),
            ])
            lln_ids = lln_rels.mapped('id_org').ids
            if not lln_ids:
                record.available_klas_ids = False
                continue
            # Find all children of lln departments
            klas_rels = PropRel.search([
                ('id_org_parent', 'in', lln_ids),
                ('id_org', '!=', False),
            ])
            record.available_klas_ids = klas_rels.mapped('id_org')

    @api.depends('school_id')
    def _expand_org_descendants(self, root_org_ids):
        """Geef root_org_ids + alle descendants terug, gevonden via ORG-TREE
        proprelations (id_org_parent → id_org). Itereert breadth-first tot er
        geen nieuwe kinderen meer gevonden worden."""
        PropRel = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree_type = PropRelationType.search(
            [('name', '=', 'ORG-TREE')], limit=1)
        if not org_tree_type or not root_org_ids:
            return list(root_org_ids)
        visited = set(root_org_ids)
        frontier = list(root_org_ids)
        while frontier:
            children_rels = PropRel.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org_parent', 'in', frontier),
                ('id_org', '!=', False),
            ])
            children_ids = children_rels.mapped('id_org').ids
            new_ids = [cid for cid in children_ids if cid not in visited]
            if not new_ids:
                break
            visited.update(new_ids)
            frontier = new_ids
        return list(visited)

    def _compute_available_leerkracht_ids(self):
        PropRel = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        OrgType = self.env['myschool.org.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        for record in self:
            if not record.school_id or not person_tree_type or not dept_type:
                record.available_leerkracht_ids = False
                continue
            # Find pers departments under the school
            pers_rels = PropRel.search([
                ('id_org_parent', '=', record.school_id.id),
                ('id_org.org_type_id', '=', dept_type.id),
                ('id_org.name_short', '=', 'pers'),
            ])
            pers_ids = pers_rels.mapped('id_org').ids
            if not pers_ids:
                record.available_leerkracht_ids = False
                continue
            # Expand pers naar alle nakomelingen (lkr, adm, dir, ...) zodat
            # leerkrachten gekoppeld aan een sub-departement ook gevonden worden.
            org_ids = record._expand_org_descendants(pers_ids)
            # Find all persons linked to pers (or any descendant) via PERSON-TREE
            person_rels = PropRel.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('id_org', 'in', org_ids),
                ('id_person', '!=', False),
                ('is_active', '=', True),
            ])
            record.available_leerkracht_ids = person_rels.mapped('id_person')

    @api.depends('leerkracht_ids')
    def _compute_leerkracht_count(self):
        for record in self:
            record.leerkracht_count = len(record.leerkracht_ids)

    def action_view_leerkrachten(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Leerkrachten - {self.titel or self.name}',
            'res_model': 'myschool.person',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.leerkracht_ids.ids)],
            'context': {'create': False},
        }

    @api.constrains('datetime', 'datetime_end')
    def _check_datetime(self):
        now = fields.Datetime.now()
        for record in self:
            if record.datetime and record.datetime < now:
                raise UserError("De startdatum en tijdstip mag niet in het verleden liggen.")
            if record.datetime and record.datetime_end and record.datetime_end <= record.datetime:
                raise UserError("De einddatum en tijdstip moet na de startdatum en tijdstip liggen.")

    @api.onchange('school_id')
    def _onchange_school_id(self):
        self.klas_ids = [(5, 0, 0)]
        self.leerkracht_ids = [(5, 0, 0)]

    @api.depends('name', 'titel')
    def _compute_display_name(self):
        for record in self:
            if record.titel:
                record.display_name = f'{record.name} - {record.titel}'
            else:
                record.display_name = record.name or ''

    _rec_names_search = ['name', 'titel']

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'De referentie moet uniek zijn.'),
    ]

    def _auto_init(self):
        res = super()._auto_init()
        # Fix any existing records with missing references
        self.env.cr.execute("""
            SELECT id FROM activiteiten_record
            WHERE name IS NULL OR name IN ('', 'New', 'new')
        """)
        broken_ids = [r[0] for r in self.env.cr.fetchall()]
        if broken_ids:
            for record_id in broken_ids:
                ref = self.env['ir.sequence'].sudo().next_by_code('activiteiten.record')
                if ref:
                    self.env.cr.execute(
                        "UPDATE activiteiten_record SET name = %s WHERE id = %s",
                        (ref, record_id)
                    )
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New' or not vals.get('name'):
                vals['name'] = self._next_reference()
            if vals.get('activity_type') and vals.get('state', 'draft') == 'draft':
                vals['state'] = 'form_invullen'
            # Houd bus_nodig synchroon met vervoer_type wanneer dat laatste
            # programmatisch gezet wordt zonder expliciete bus_nodig waarde.
            if 'vervoer_type' in vals and 'bus_nodig' not in vals:
                vals['bus_nodig'] = (vals.get('vervoer_type') == 'bus')
        records = super().create(vals_list)
        # Fix any records that still ended up without a proper reference
        for record in records:
            if not record.name or record.name == 'New':
                record.sudo().name = self._next_reference()
        # Auto-add the creator as a teacher with an accepted invite
        for record in records:
            person = self.env['myschool.person'].sudo().search(
                [('odoo_user_id', '=', record.create_uid.id)], limit=1)
            if person:
                record.sudo().leerkracht_ids = [(4, person.id)]
                self.env['activiteiten.invite'].sudo().create({
                    'activiteit_id': record.id,
                    'person_id': person.id,
                })
        return records

    def write(self, vals):
        if 'vervoer_type' in vals and 'bus_nodig' not in vals:
            vals['bus_nodig'] = (vals.get('vervoer_type') == 'bus')
        res = super().write(vals)
        for record in self:
            if not record.name or record.name == 'New':
                record.sudo().name = self._next_reference()
        return res

    def _next_reference(self):
        """Get next unique reference, syncing the sequence if needed."""
        last_record = self.sudo().search(
            [('name', 'like', 'ACT-')],
            order='name desc', limit=1,
        )
        last_number = 0
        if last_record:
            try:
                last_number = int(last_record.name.replace('ACT-', ''))
            except ValueError:
                pass
        # Search without company filter to find the sequence regardless
        seq = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'activiteiten.record'),
        ], limit=1)
        if not seq:
            seq = self.env['ir.sequence'].sudo().create({
                'name': 'Activiteiten',
                'code': 'activiteiten.record',
                'prefix': 'ACT-',
                'padding': 5,
                'number_next': last_number + 1,
                'number_increment': 1,
                'company_id': False,
            })
            _logger.info('[ACT] Auto-created ir.sequence for activiteiten.record')
        if seq.number_next <= last_number:
            seq.sudo().write({'number_next': last_number + 1})
        # Call _next() directly on the sequence to bypass company filtering
        ref = seq.sudo()._next()
        _logger.info('[ACT] Generated reference: %s', ref)
        return ref

    # --- Personeelslid actions ---

    @api.onchange('activity_type')
    def _onchange_activity_type(self):
        if self.activity_type and self.state == 'draft':
            self.state = 'form_invullen'

    def action_submit_form(self):
        for record in self:
            if record.state not in ('draft', 'form_invullen', 'bus_refused'):
                raise UserError("Het formulier kan alleen vanuit de invulfase ingediend worden.")
            if not record.titel:
                raise UserError("Vul een titel in.")
            if not record.datetime:
                raise UserError("Vul een datum en tijdstip in.")
            # Snapshot students and teachers at submission time
            record._create_snapshot()
            if record.bus_nodig:
                record.state = 'bus_check'
            else:
                record.state = 'pending_approval'
        self._send_notification('submit')
        pending_records = self.filtered(lambda r: r.state == 'pending_approval')
        if pending_records:
            pending_records._schedule_directie_activity()

    # --- Aankoop actions ---

    def action_bus_approved(self):
        for record in self:
            if record.state != 'bus_check':
                raise UserError("Bus controle is niet van toepassing.")
            record.bus_available = True
            record.state = 'pending_approval'
        self._send_notification('bus_approved')
        self._send_notification('submit')
        self._schedule_directie_activity()

    def action_bus_refused(self):
        for record in self:
            if record.state != 'bus_check':
                raise UserError("Bus controle is niet van toepassing.")
            record.bus_available = False
            record.state = 'bus_refused'
        self._send_notification('bus_refused')

    def action_open_busverdeling(self):
        self.ensure_one()
        # Auto-create bus records if they don't exist yet
        aantal = int(self.aantal_bussen or '1')
        existing = self.bus_ids.mapped('bus_nummer')
        for nr in range(1, aantal + 1):
            if nr not in existing:
                self.env['activiteiten.bus'].create({
                    'activiteit_id': self.id,
                    'bus_nummer': nr,
                })
        return {
            'type': 'ir.actions.act_window',
            'name': f'Busverdeling — {self.name}',
            'res_model': 'activiteiten.bus',
            'view_mode': 'list,form',
            'domain': [('activiteit_id', '=', self.id)],
            'context': {
                'default_activiteit_id': self.id,
                'allowed_klas_ids': self.klas_ids.ids,
                'allowed_leerkracht_ids': self.leerkracht_ids.ids,
            },
        }

    # --- Directie actions ---

    def action_approve(self):
        for record in self:
            if record.state != 'pending_approval':
                raise UserError("Alleen aanvragen in afwachting kunnen goedgekeurd worden.")
            # Voeg alle uitgenodigde leerkrachten toe aan leerkracht_ids en breng hen op de hoogte
            persons_to_add = record.invite_ids.mapped('person_id').filtered(
                lambda p: p not in record.leerkracht_ids
            )
            if persons_to_add:
                record.write({
                    'leerkracht_ids': [(4, p.id) for p in persons_to_add],
                })
            record.invite_ids._notify_invited_person()
            record.state = 's_code'
        self._send_notification('approved')
        self._schedule_owner_approved_activity()
        self._schedule_boekhouding_activity()

    def action_reject(self):
        for record in self:
            if record.state != 'pending_approval':
                raise UserError("Alleen aanvragen in afwachting kunnen afgekeurd worden.")
            if not (record.rejection_reason or '').strip():
                raise UserError("Vul eerst een reden voor afkeuring in voordat u de aanvraag afkeurt.")
            record.state = 'rejected'
        self._send_notification('rejected')
        bus_records = self.filtered(lambda r: r.bus_nodig and r.bus_available)
        if bus_records:
            bus_records._schedule_aankoop_bus_vrijgekomen()

    # --- Boekhouding actions ---

    def _is_multiday(self):
        """Check if the activity spans 2 or more days."""
        self.ensure_one()
        if not self.datetime or not self.datetime_end:
            return False
        return self.datetime.date() != self.datetime_end.date()

    def action_confirm_s_code(self):
        pct = self._get_verzekering_pct()
        for record in self:
            if record.state != 's_code':
                raise UserError("S-Code kan alleen in de S-Code fase bevestigd worden.")
            if not record.s_code_name:
                raise UserError("Vul eerst de S-Code in.")
            # Remove any existing auto lines and recreate them
            auto_lines_to_remove = record.kosten_ids.filtered(lambda l: l.is_auto)
            if auto_lines_to_remove:
                auto_lines_to_remove.with_context(force_unlink_auto=True).unlink()
            auto_lines = []
            if record.bus_price:
                auto_lines.append({
                    'activiteit_id': record.id,
                    'omschrijving': 'Bus',
                    'bedrag': record.bus_price,
                    'kosten_type': 'vast',
                    'is_auto': True,
                })
            # Only add verzekering for multi-day activities (2+ days)
            if record._is_multiday():
                manual_total = sum(
                    l.bedrag for l in record.kosten_ids if not l.is_auto)
                basis_bedrag = (record.bus_price or 0) + manual_total
                verzekering_bedrag = basis_bedrag * (pct / 100.0)
                auto_lines.append({
                    'activiteit_id': record.id,
                    'omschrijving': 'Verzekering (%.1f%%)' % pct,
                    'bedrag': verzekering_bedrag,
                    'kosten_type': 'vast',
                    'is_auto': True,
                })
                record.verzekering_done = True
            else:
                record.verzekering_done = False
            if auto_lines:
                self.env['activiteiten.kosten.line'].create(auto_lines)
            record.state = 'done'
        self._schedule_vervangingen_activity()

    # --- Shared actions ---

    def action_reset_to_form(self):
        for record in self:
            if record.state not in ('rejected', 'bus_refused'):
                raise UserError(
                    "Alleen afgekeurde of bus-geweigerde aanvragen kunnen opnieuw ingediend worden.")
            record.state = 'form_invullen'
            record.rejection_reason = False

    def _check_done(self):
        for record in self:
            if record.verzekering_done:
                record.state = 'done'

    def write(self, vals):
        res = super().write(vals)
        if 'bus_price' in vals:
            self._recalculate_auto_lines()
        return res

    def _recalculate_auto_lines(self):
        pct = self._get_verzekering_pct() / 100.0
        for record in self:
            record.invalidate_recordset(['kosten_ids'])
            verzekering_line = record.kosten_ids.filtered(
                lambda l: l.is_auto and 'Verzekering' in (l.omschrijving or ''))
            bus_line = record.kosten_ids.filtered(
                lambda l: l.is_auto and l.omschrijving == 'Bus')
            if bus_line and record.bus_price:
                bus_line.write({'bedrag': record.bus_price})
            if not verzekering_line:
                continue
            other_total = sum(
                l.bedrag for l in record.kosten_ids if l.id != verzekering_line.id)
            verzekering_line.write({'bedrag': other_total * pct})

    def unlink(self):
        is_admin = self.env.user.has_group('activiteiten.group_activiteiten_admin')
        for record in self:
            if not is_admin:
                if record.state not in ('draft', 'form_invullen'):
                    raise UserError("U kunt alleen aanvragen verwijderen die nog niet ingediend zijn.")
                if record.create_uid.id != self.env.uid:
                    raise UserError("U kunt alleen uw eigen aanvragen verwijderen.")
        return super().unlink()

    def action_delete(self):
        self.unlink()
        # Generieke client-action die terugkeert naar de vorige controller
        # zodat filters/sortering/scroll behouden blijven (zie myschool_core).
        return {
            'type': 'ir.actions.client',
            'tag': 'myschool_back_to_previous',
            'params': {
                'fallback_action': 'activiteiten.action_activiteiten_main',
            },
        }

    def _schedule_owner_approved_activity(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            if record.create_uid:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Activiteit goedgekeurd',
                    note=f'Uw activiteit "{record.titel}" is goedgekeurd.',
                    user_id=record.create_uid.id,
                )

    def _schedule_vervangingen_activity(self):
        vervangingen_group = self.env.ref(
            'activiteiten.group_activiteiten_vervangingen', raise_if_not_found=False)
        if not vervangingen_group:
            return
        vervangingen_users = vervangingen_group.user_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in vervangingen_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Vervanging inplannen via Planner',
                    note=f'De S-Code voor activiteit "{record.titel}" is ingevuld. '
                         f'Maak een inhaalplan aan in de Planner en dien het in om de vervanging af te ronden.',
                    user_id=user.id,
                )

    def _notify_vervangingen_new_invites(self, invites):
        """Notify vervangingen team when new teachers are invited after activity is past approval."""
        vervangingen_group = self.env.ref(
            'activiteiten.group_activiteiten_vervangingen', raise_if_not_found=False)
        if not vervangingen_group:
            return
        vervangingen_users = vervangingen_group.user_ids
        if not vervangingen_users:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        names = ', '.join(invites.mapped('person_id.name'))
        for record in self:
            partner_ids = vervangingen_users.mapped('partner_id').ids
            record.message_post(
                body=(
                    '<p><strong>Vervanging update:</strong> Nieuwe uitnodiging(en) verstuurd '
                    'voor activiteit <strong>%s</strong> aan: %s. '
                    'De vervanging moet mogelijk aangepast worden.</p>'
                ) % (record.titel, names),
                partner_ids=partner_ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            for user in vervangingen_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Vervanging aanpassen: %s' % record.titel,
                    note='Nieuwe leerkracht(en) uitgenodigd: %s. Controleer de vervanging.' % names,
                    user_id=user.id,
                )

    def _schedule_directie_activity(self):
        directie_group = self.env.ref(
            'activiteiten.group_activiteiten_directie', raise_if_not_found=False)
        if not directie_group:
            return
        directie_users = directie_group.user_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in directie_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Activiteit goedkeuren',
                    note=f'Er is een nieuwe aanvraag "{record.titel}" ingediend door {record.create_uid.name}. Gelieve deze te beoordelen.',
                    user_id=user.id,
                )

    def _schedule_boekhouding_activity(self):
        boekhouding_group = self.env.ref(
            'activiteiten.group_activiteiten_boekhouding', raise_if_not_found=False)
        if not boekhouding_group:
            return
        boekhouding_users = boekhouding_group.user_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in boekhouding_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='S-Code invullen',
                    note=f'De activiteit "{record.titel}" is goedgekeurd. Gelieve de S-Code in te vullen.',
                    user_id=user.id,
                )

    def _schedule_aankoop_bus_vrijgekomen(self):
        aankoop_group = self.env.ref(
            'activiteiten.group_activiteiten_aankoop', raise_if_not_found=False)
        if not aankoop_group:
            return
        aankoop_users = aankoop_group.user_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in aankoop_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Bus vrijgekomen',
                    note=f'De activiteit "{record.titel}" is afgekeurd. De bus die hiervoor was gereserveerd is weer beschikbaar.',
                    user_id=user.id,
                )

    _NOTIFICATION_TEMPLATES = {
        'submit': 'activiteiten.email_template_notify_directie',
        'approved': 'activiteiten.email_template_approved',
        'rejected': 'activiteiten.email_template_rejected',
        'bus_refused': 'activiteiten.email_template_bus_refused',
        'bus_approved': 'activiteiten.email_template_bus_approved',
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
