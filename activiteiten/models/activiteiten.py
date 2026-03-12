from markupsafe import Markup

from odoo import models, fields, api
from odoo.exceptions import UserError


class Activiteiten(models.Model):
    _name = 'activiteiten.record'
    _description = 'Activiteiten'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referentie',
        required=True,
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
        default=lambda self: self.env.user.school_ids[:1],
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
        ('form_invullen', 'Formulier invullen'),
        ('bus_check', 'Controle bus'),
        ('bus_refused', 'Bus geweigerd'),
        ('pending_approval', 'Wacht op goedkeuring'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('s_code', 'S-Code controle'),
        ('vervanging', 'Vervanging inplannen'),
        ('done', 'Afgerond'),
    ], string='Status', default='draft', required=True, tracking=True)

    bus_nodig = fields.Boolean(string='Bus nodig', default=False)
    bus_price = fields.Monetary(
        string='Prijs van bus',
        currency_field='currency_id',
    )
    bus_available = fields.Boolean(string='Bus beschikbaar')
    s_code_name = fields.Char(string='S-Code')
    s_code_price = fields.Monetary(
        string='S-Code bedrag',
        currency_field='currency_id',
    )
    kosten_ids = fields.One2many(
        'activiteiten.kosten.line', 'activiteit_id',
        string='Kosten',
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
    verzekering_done = fields.Boolean(string='Verzekering geregeld', default=False)
    rejection_reason = fields.Text(string='Reden voor afkeuring')
    student_count = fields.Integer(
        string='Aantal leerlingen',
        compute='_compute_student_count',
    )
    is_owner = fields.Boolean(compute='_compute_is_owner')
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

    def action_view_students(self):
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        person_ids = []
        if person_tree_type and self.klas_ids:
            rels = PropRelation.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('id_org', 'in', self.klas_ids.ids),
                ('id_person', '!=', False),
                ('is_active', '=', True),
            ])
            person_ids = rels.mapped('id_person').ids
        return {
            'type': 'ir.actions.act_window',
            'name': f'Leerlingen - {self.titel or self.name}',
            'res_model': 'myschool.person',
            'view_mode': 'list,form',
            'domain': [('id', 'in', person_ids)],
            'context': {'create': False},
        }

    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = record.create_uid.id == self.env.uid

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

    @api.depends('s_code_price', 'kosten_ids.bedrag')
    def _compute_totale_kost(self):
        for record in self:
            record.totale_kost = (record.s_code_price or 0) + sum(record.kosten_ids.mapped('bedrag'))

    @api.onchange('s_code_price', 'bus_price', 'kosten_ids')
    def _onchange_recalculate_verzekering(self):
        verzekering_line = None
        other_total = self.s_code_price or 0
        for line in self.kosten_ids:
            if line.is_auto and 'Verzekering' in (line.omschrijving or ''):
                verzekering_line = line
            elif line.is_auto and line.omschrijving == 'Bus' and self.bus_price:
                line.bedrag = self.bus_price
                other_total += line.bedrag or 0
            else:
                other_total += line.bedrag or 0
        if verzekering_line:
            verzekering_line.bedrag = other_total * 0.02

    @api.depends('s_code_price', 'kosten_ids.bedrag', 'kosten_ids.omschrijving')
    def _compute_kosten_display(self):
        for record in self:
            lines = []
            if record.s_code_price:
                lines.append('S-Code: € %.2f' % record.s_code_price)
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
            # Find all persons linked to pers departments via PERSON-TREE
            person_rels = PropRel.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('id_org', 'in', pers_ids),
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

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'leerkracht_ids' in fields_list:
            person = self.env['myschool.person'].search(
                [('odoo_user_id', '=', self.env.uid)], limit=1)
            if person:
                defaults['leerkracht_ids'] = [(6, 0, [person.id])]
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self._next_reference()
            if vals.get('activity_type') and vals.get('state', 'draft') == 'draft':
                vals['state'] = 'form_invullen'
        return super().create(vals_list)

    def _next_reference(self):
        """Get next unique reference, syncing the sequence if needed."""
        last_record = self.search(
            [('name', 'like', 'ACT-')],
            order='name desc', limit=1,
        )
        last_number = 0
        if last_record:
            try:
                last_number = int(last_record.name.replace('ACT-', ''))
            except ValueError:
                pass
        seq = self.env['ir.sequence'].search([
            ('code', '=', 'activiteiten.record'),
        ], limit=1)
        if not seq:
            raise UserError("Sequentie 'activiteiten.record' niet gevonden.")
        if seq.number_next <= last_number:
            seq.sudo().write({'number_next': last_number + 1})
        return self.env['ir.sequence'].next_by_code('activiteiten.record')

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
            if record.bus_nodig:
                record.state = 'bus_check'
            else:
                record.state = 'pending_approval'
        self._send_notification('submit')

    # --- Aankoop actions ---

    def action_bus_approved(self):
        for record in self:
            if record.state != 'bus_check':
                raise UserError("Bus controle is niet van toepassing.")
            record.bus_available = True
            record.state = 'pending_approval'
        self._send_notification('submit')

    def action_bus_refused(self):
        for record in self:
            if record.state != 'bus_check':
                raise UserError("Bus controle is niet van toepassing.")
            record.bus_available = False
            record.state = 'bus_refused'
        self._send_notification('bus_refused')

    # --- Directie actions ---

    def action_approve(self):
        for record in self:
            if record.state != 'pending_approval':
                raise UserError("Alleen aanvragen in afwachting kunnen goedgekeurd worden.")
            if record.activity_type == 'binnenschools':
                record.state = 'done'
            else:
                record.state = 's_code'
        self._send_notification('approved')
        self._schedule_owner_approved_activity()
        buitenschools = self.filtered(lambda r: r.activity_type == 'buitenschools')
        if buitenschools:
            buitenschools._schedule_boekhouding_activity()
        binnenschools = self.filtered(lambda r: r.activity_type == 'binnenschools')
        if binnenschools:
            binnenschools._schedule_vervangingen_activity()

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

    def action_confirm_s_code(self):
        for record in self:
            if record.state != 's_code':
                raise UserError("S-Code kan alleen in de S-Code fase bevestigd worden.")
            if not record.s_code_name:
                raise UserError("Vul eerst de S-Code in.")
            if not record.s_code_price:
                raise UserError("Vul eerst het S-Code bedrag in.")
            # Remove any existing auto lines and recreate them
            record.kosten_ids.filtered(lambda l: l.is_auto).unlink()
            auto_lines = []
            if record.bus_price:
                auto_lines.append({
                    'activiteit_id': record.id,
                    'omschrijving': 'Bus',
                    'bedrag': record.bus_price,
                    'is_auto': True,
                })
            basis_bedrag = record.s_code_price + (record.bus_price or 0)
            verzekering_bedrag = basis_bedrag * 0.02
            auto_lines.append({
                'activiteit_id': record.id,
                'omschrijving': 'Verzekering (2%)',
                'bedrag': verzekering_bedrag,
                'is_auto': True,
            })
            self.env['activiteiten.kosten.line'].create(auto_lines)
            record.verzekering_done = True
            record.state = 'done'
        self._schedule_vervangingen_activity()

    def action_verzekering_done(self):
        for record in self:
            if record.state not in ('s_code', 'vervanging'):
                raise UserError("Verzekering kan alleen bij S-Code of vervanging afgehandeld worden.")
            record.verzekering_done = True
            record._check_done()

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
        if 's_code_price' in vals or 'bus_price' in vals:
            self._recalculate_auto_lines()
        return res

    def _recalculate_auto_lines(self):
        for record in self:
            verzekering_line = record.kosten_ids.filtered(
                lambda l: l.is_auto and 'Verzekering' in (l.omschrijving or ''))
            bus_line = record.kosten_ids.filtered(
                lambda l: l.is_auto and l.omschrijving == 'Bus')
            if not verzekering_line:
                continue
            # Update bus line amount
            if bus_line and record.bus_price:
                bus_line.write({'bedrag': record.bus_price})
            # Recalculate verzekering (2% of all costs except verzekering itself)
            other_total = (record.s_code_price or 0) + sum(
                l.bedrag for l in record.kosten_ids if l.id != verzekering_line.id)
            verzekering_line.write({'bedrag': other_total * 0.02})

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
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

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
