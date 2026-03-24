import ast

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class IrActionsActWindow(models.Model):
    _inherit = 'ir.actions.act_window'

    def _get_action_dict(self):
        result = super()._get_action_dict()
        if result.get('res_model') == 'professionalisering.record':
            raw_ctx = result.get('context') or '{}'
            if isinstance(raw_ctx, str):
                try:
                    ctx = ast.literal_eval(raw_ctx)
                except (ValueError, SyntaxError):
                    ctx = {}
            else:
                ctx = dict(raw_ctx)
            if not any(k.startswith('search_default_') for k in ctx):
                user = self.env.user
                if user.has_group('professionalisering.group_professionalisering_admin'):
                    pass
                elif user.has_group('professionalisering.group_professionalisering_boekhouding'):
                    ctx['search_default_payment_pending'] = 1
                elif user.has_group('professionalisering.group_professionalisering_directie'):
                    ctx['search_default_to_approve'] = 1
                elif user.has_group('professionalisering.group_professionalisering_vervangingen'):
                    ctx['search_default_replacement_pending'] = 1
                else:
                    ctx['search_default_my_requests'] = 1
                result['context'] = ctx
        return result


class ProfessionaliseringRecord(models.Model):
    _name = 'professionalisering.record'
    _description = 'Professionalisering'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referentie',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
    type = fields.Selection([
        ('individueel', 'Individuele'),
        ('teamleren', 'Teamleren'),
    ], string='Type', required=True)
    subtype_individueel = fields.Selection([
        ('cursus', 'Cursus'),
        ('workshop', 'Workshop'),
        ('lezen', 'Lezen'),
        ('video', 'Video'),
        ('podcast', 'Podcast'),
        ('interne_opvolging', 'Interne opvolging'),
    ], string='Vorm')
    subtype_teamleren = fields.Selection([
        ('plc', 'Professional Learning Community (PLC)'),
        ('samen_studie', 'Samen studie'),
        ('intervisie', 'Intervisie'),
        ('co_teaching', 'Co-teaching'),
    ], string='Vorm')
    titel = fields.Char(string='Titel opleiding', required=True)
    invite_ids = fields.One2many('professionalisering.invite', 'professionalisering_id', string='Uitnodigingen')
    has_pending_invites = fields.Boolean(compute='_compute_has_pending_invites')
    show_invites = fields.Boolean(compute='_compute_show_invites')
    current_user_invited = fields.Boolean(compute='_compute_current_user_invite')
    current_user_invite_state = fields.Selection([
        ('pending', 'In afwachting'),
        ('accepted', 'Geaccepteerd'),
        ('rejected', 'Geweigerd'),
    ], compute='_compute_current_user_invite')
    description = fields.Text(string='Beschrijving')
    employee_id = fields.Many2one(
        'hr.employee',
        string='Medewerker',
        required=True,
        default=lambda self: self.env.user.employee_ids[:1],
    )
    school_id = fields.Many2one(
        'myschool.org',
        string='School',
        required=True,
        default=lambda self: self.env.company.school_id or self.env.user.school_ids[:1],
        domain="[('id', 'in', allowed_school_json)]",
    )
    allowed_school_json = fields.Json(
        compute='_compute_allowed_school_json',
    )
    is_owner = fields.Boolean(compute='_compute_is_owner')
    is_admin = fields.Boolean(compute='_compute_is_admin')
    start_date = fields.Date(string='Startdatum', required=True)
    end_date = fields.Date(string='Einddatum')
    verschillende_dagen = fields.Boolean(string='Verschillende dagen', default=False)
    date_line_ids = fields.One2many('professionalisering.date.line', 'professionalisering_id', string='Datums')
    dates_display = fields.Html(string='Datums', compute='_compute_dates_display', sanitize=False)
    cost = fields.Monetary(string='Geschatte kost', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Munteenheid',
        default=lambda self: self.env.company.currency_id,
    )
    total_cost = fields.Monetary(
        string='Totale kost', currency_field='currency_id',
        compute='_compute_total_cost',
    )
    s_code_name = fields.Char(string='S-Code')
    s_code_price = fields.Monetary(
        string='S-Code bedrag', currency_field='currency_id',
    )
    kosten_ids = fields.One2many(
        'professionalisering.kosten.line', 'professionalisering_id',
        string='Kosten',
    )
    totale_kost = fields.Monetary(
        string='Totale kost (S-Code + extra)',
        currency_field='currency_id',
        compute='_compute_totale_kost',
    )
    vak = fields.Selection([
        ('wiskunde', 'Wiskunde'),
        ('nederlands', 'Nederlands'),
        ('frans', 'Frans'),
        ('engels', 'Engels'),
        ('wetenschap', 'Wetenschap'),
        ('geschiedenis', 'Geschiedenis'),
        ('aardrijkskunde', 'Aardrijkskunde'),
        ('lichamelijke_opvoeding', 'Lichamelijke opvoeding'),
        ('informatica', 'Informatica'),
        ('muziek', 'Muziek'),
        ('andere', 'Andere'),
    ], string='Vak')
    state = fields.Selection([
        ('selection_of_form', 'Formulier kiezen'),
        ('fill_in_form_individueel', 'Ingediend'),
        ('fill_in_form_teamleren', 'Ingediend'),
        ('bevestiging', 'Bevestigd'),
        ('weigering', 'Geweigerd'),
        ('done', 'Afgerond'),
    ], string='Status', default='selection_of_form', tracking=True)
    rejection_reason = fields.Text(string='Reden voor afkeuring')
    assigned_to = fields.Many2one(
        'hr.employee',
        string='Toegewezen aan',
        tracking=True,
        domain=lambda self: [('user_id', 'in',
            self.env.ref('professionalisering.group_professionalisering_directie').all_user_ids.ids
        )],
    )
    directie_id = fields.Many2one(
        'hr.employee',
        string='Beoordeeld door',
        readonly=True,
    )
    payment_done = fields.Boolean(string='Betaling bevestigd', default=False)
    bewijs_link = fields.Char(string='Link (video, podcast, ...)')
    bewijs_beschrijving = fields.Text(string='Beschrijving bewijs')
    bewijs_document_ids = fields.Many2many(
        'ir.attachment', string='Documenten',
        help='Upload een attest, certificaat of ander bewijs.',
    )
    bewijs_ingediend = fields.Boolean(string='Bewijs ingediend', default=False)
    priority = fields.Selection([
        ('0', 'Normaal'),
        ('1', 'Laag'),
        ('2', 'Hoog'),
        ('3', 'Urgent'),
    ], string='Prioriteit', default='0')

    @api.depends_context('uid', 'company')
    def _compute_allowed_school_json(self):
        schools = self.env.company.school_id or self.env.user.school_ids
        ids = schools.ids or self.env['myschool.org'].sudo().search([('org_type_id.name', '=', 'SCHOOL'), ('is_active', '=', True)]).ids
        for record in self:
            record.allowed_school_json = ids

    @api.depends('invite_ids', 'invite_ids.employee_id', 'invite_ids.state')
    @api.depends_context('uid')
    def _compute_current_user_invite(self):
        for record in self:
            invite = record.invite_ids.filtered(
                lambda i: i.employee_id.user_id == self.env.user
            )[:1]
            record.current_user_invited = bool(invite)
            record.current_user_invite_state = invite.state if invite else False

    @api.depends('invite_ids.state')
    def _compute_has_pending_invites(self):
        for record in self:
            record.has_pending_invites = any(
                inv.state == 'pending' for inv in record.invite_ids
            )

    @api.depends('type', 'subtype_individueel')
    def _compute_show_invites(self):
        for record in self:
            record.show_invites = (
                record.type == 'teamleren'
                or (record.type == 'individueel'
                    and record.subtype_individueel in ('cursus', 'workshop'))
            )

    @api.onchange('type')
    def _onchange_type(self):
        self.subtype_individueel = False
        self.subtype_teamleren = False

    @api.depends('employee_id')
    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = record.employee_id and record.employee_id.user_id == self.env.user

    @api.depends_context('uid')
    def _compute_is_admin(self):
        is_admin = self.env.user.has_group('professionalisering.group_professionalisering_admin')
        for record in self:
            record.is_admin = is_admin

    @api.depends('verschillende_dagen', 'start_date', 'end_date', 'date_line_ids.date', 'date_line_ids.cost')
    def _compute_dates_display(self):
        for record in self:
            if record.verschillende_dagen:
                all_dates = []
                if record.start_date:
                    all_dates.append('%s &nbsp;-&nbsp; €%.2f' % (
                        record.start_date.strftime('%d %b %Y'), record.cost or 0,
                    ))
                for line in record.date_line_ids.sorted('date'):
                    if line.date:
                        all_dates.append('%s &nbsp;-&nbsp; €%.2f' % (
                            line.date.strftime('%d %b %Y'), line.cost or 0,
                        ))
                record.dates_display = '<br/>'.join(all_dates)
            elif record.start_date and record.end_date and record.end_date != record.start_date:
                record.dates_display = '%s → %s' % (
                    record.start_date.strftime('%d %b %Y'),
                    record.end_date.strftime('%d %b %Y'),
                )
            elif record.start_date:
                record.dates_display = record.start_date.strftime('%d %b %Y')
            else:
                record.dates_display = ''

    @api.depends('verschillende_dagen', 'cost', 'date_line_ids.cost')
    def _compute_total_cost(self):
        for record in self:
            if record.verschillende_dagen:
                record.total_cost = (record.cost or 0) + sum(
                    record.date_line_ids.mapped('cost'))
            else:
                record.total_cost = record.cost or 0

    @api.depends('s_code_price', 'kosten_ids.bedrag')
    def _compute_totale_kost(self):
        for record in self:
            record.totale_kost = (record.s_code_price or 0) + sum(record.kosten_ids.mapped('bedrag'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                sequence = self.env['ir.sequence'].next_by_code('professionalisering.record')
                if not sequence:
                    raise UserError("Sequentie 'professionalisering.record' niet gevonden.")
                vals['name'] = sequence
        return super().create(vals_list)

    @api.model
    def _get_submitted_states(self):
        return ['fill_in_form_individueel', 'fill_in_form_teamleren']

    def action_submit(self):
        type_state_map = {
            'individueel': 'fill_in_form_individueel',
            'teamleren': 'fill_in_form_teamleren',
        }
        for record in self:
            if record.state != 'selection_of_form':
                raise UserError("Alleen conceptaanvragen kunnen ingediend worden.")
            if record.has_pending_invites:
                raise UserError("Niet alle uitnodigingen zijn beantwoord. Wacht tot alle collega's hebben gereageerd.")
            new_state = type_state_map.get(record.type)
            if not new_state:
                raise UserError("Selecteer eerst een type professionalisering.")
            record.state = new_state
        self._send_notification('professionalisering.email_template_notify_directie')

    def action_approve(self):
        submitted_states = self._get_submitted_states()
        for record in self:
            if record.state not in submitted_states:
                raise UserError("Alleen ingediende aanvragen kunnen goedgekeurd worden.")
            record.state = 'bevestiging'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification('professionalisering.email_template_notify_employee_approved')
        self._schedule_vervangingen_activity()

    def action_reject(self):
        submitted_states = self._get_submitted_states()
        for record in self:
            if record.state not in submitted_states:
                raise UserError("Alleen ingediende aanvragen kunnen afgekeurd worden.")
            record.state = 'weigering'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification('professionalisering.email_template_notify_employee_rejected')

    def action_confirm_payment(self):
        for record in self:
            if record.state != 'bevestiging':
                raise UserError("Betaling kan alleen bevestigd worden voor goedgekeurde aanvragen.")
            if not record.s_code_name:
                raise UserError("Vul eerst de S-Code in.")
            if not record.s_code_price:
                raise UserError("Vul eerst het S-Code bedrag in.")
            # Remove existing auto lines and recreate
            auto_lines = record.kosten_ids.filtered(lambda l: l.is_auto)
            if auto_lines:
                auto_lines.with_context(force_unlink_auto=True).unlink()
            # Calculate verzekering (2% of all costs)
            manual_total = sum(l.bedrag for l in record.kosten_ids if not l.is_auto)
            basis_bedrag = (record.s_code_price or 0) + manual_total
            verzekering_bedrag = basis_bedrag * 0.02
            self.env['professionalisering.kosten.line'].create({
                'professionalisering_id': record.id,
                'omschrijving': 'Verzekering (2%)',
                'bedrag': verzekering_bedrag,
                'is_auto': True,
            })
            record.payment_done = True
            record.state = 'done'
        self._schedule_bewijs_activity()

    def action_reset_draft(self):
        for record in self:
            if record.state != 'weigering':
                raise UserError("Alleen afgekeurde aanvragen kunnen opnieuw ingediend worden.")
            record.state = 'selection_of_form'
            record.rejection_reason = False
            record.directie_id = False

    def _schedule_bewijs_activity(self):
        """Notify the owner to upload proof after completion."""
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            if not record.employee_id.user_id:
                continue
            record.activity_schedule(
                activity_type_id=activity_type.id if activity_type else False,
                summary='Bewijs uploaden: %s' % record.titel,
                note='Uw professionalisering "%s" is afgerond. '
                     'Gelieve een bewijs te uploaden (attest, link naar video/podcast, ...).' % record.titel,
                user_id=record.employee_id.user_id.id,
            )

    def action_submit_bewijs(self):
        for record in self:
            if record.state != 'done':
                raise UserError("Bewijs kan alleen ingediend worden voor afgeronde aanvragen.")
            subtype = record.subtype_individueel
            if subtype in ('video', 'podcast') and not record.bewijs_link:
                raise UserError("Voeg een link toe als bewijs.")
            elif subtype in ('lezen', 'interne_opvolging') and not record.bewijs_beschrijving:
                raise UserError("Voeg een beschrijving toe als bewijs.")
            elif subtype in ('cursus', 'workshop') and not record.bewijs_document_ids:
                raise UserError("Upload een attest of certificaat als bewijs.")
            elif record.type == 'teamleren' and not record.bewijs_beschrijving and not record.bewijs_document_ids:
                raise UserError("Voeg een verslag of document toe als bewijs.")
            record.bewijs_ingediend = True
            # Mark the bewijs activity as done
            activities = record.activity_ids.filtered(
                lambda a: a.user_id == record.employee_id.user_id
                and 'Bewijs uploaden' in (a.summary or '')
            )
            activities.action_done()

    def _schedule_vervangingen_activity(self):
        vervangingen_group = self.env.ref(
            'professionalisering.group_professionalisering_vervangingen', raise_if_not_found=False)
        if not vervangingen_group:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in vervangingen_group.user_ids:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Vervanging inplannen via Planner',
                    note='De professionalisering "%s" van %s is goedgekeurd. '
                         'Maak een vervangingsplan aan in de Planner.' % (record.titel, record.employee_id.name),
                    user_id=user.id,
                )

    @api.constrains('date_line_ids', 'start_date')
    def _check_date_lines(self):
        today = fields.Date.context_today(self)
        for record in self:
            for line in record.date_line_ids:
                if record.start_date and line.date < record.start_date:
                    raise ValidationError("Elke datum moet op of na de startdatum liggen.")
                if line.date < today:
                    raise ValidationError("Elke datum moet vandaag of in de toekomst liggen.")

    @api.constrains('start_date', 'end_date', 'verschillende_dagen')
    def _check_end_date(self):
        for record in self:
            if not record.verschillende_dagen and record.end_date and record.start_date:
                if record.end_date < record.start_date:
                    raise ValidationError("De einddatum moet op of na de startdatum liggen.")

    def _get_current_user_invite(self):
        self.ensure_one()
        invite = self.invite_ids.filtered(
            lambda i: i.employee_id.user_id == self.env.user and i.state == 'pending'
        )[:1]
        if not invite:
            raise UserError("U heeft geen openstaande uitnodiging voor deze aanvraag.")
        return invite

    def action_send_invites(self):
        for record in self:
            unsent = record.invite_ids.filtered(lambda i: not i.notified and i.state == 'pending')
            if not unsent:
                raise UserError("Er zijn geen nieuwe uitnodigingen om te versturen.")
            unsent._notify_invited_employee()
            unsent.write({'notified': True})

    def action_accept_invite(self):
        for record in self:
            record._get_current_user_invite().action_accept()

    def action_reject_invite(self):
        for record in self:
            record._get_current_user_invite().action_reject()

    def action_delete(self):
        self.unlink()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def _send_notification(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for record in self:
                template.send_mail(record.id, force_send=True)


class ProfessionaliseringInvite(models.Model):
    _name = 'professionalisering.invite'
    _description = 'Professionalisering Uitnodiging'
    _inherit = ['mail.thread']
    _rec_name = 'employee_id'

    professionalisering_id = fields.Many2one(
        'professionalisering.record', required=True, ondelete='cascade',
    )
    professionalisering_titel = fields.Char(
        related='professionalisering_id.titel', string='Opleiding',
    )
    professionalisering_state = fields.Selection(
        related='professionalisering_id.state', string='Status aanvraag',
    )
    invited_by = fields.Many2one(
        related='professionalisering_id.employee_id', string='Uitgenodigd door',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Collega', required=True,
    )
    state = fields.Selection([
        ('pending', 'In afwachting'),
        ('accepted', 'Geaccepteerd'),
        ('rejected', 'Geweigerd'),
    ], string='Status', default='pending', tracking=True)
    notified = fields.Boolean(default=False)

    def _notify_invited_employee(self):
        """Send an Odoo notification for the invited employee."""
        for invite in self:
            if not invite.employee_id.user_id:
                continue
            prof = invite.professionalisering_id
            prof.message_post(
                body=(
                    '<p>Beste %s,</p>'
                    '<p><strong>%s</strong> heeft u uitgenodigd voor de opleiding '
                    '<strong>%s</strong>.</p>'
                    '<p>Open deze aanvraag om de uitnodiging te accepteren of te weigeren.</p>'
                ) % (invite.employee_id.name, prof.employee_id.name, prof.titel),
                partner_ids=invite.employee_id.user_id.partner_id.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            prof.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=invite.employee_id.user_id.id,
                summary='Uitnodiging professionalisering: %s' % prof.titel,
                note='%s heeft u uitgenodigd. Open deze aanvraag om te accepteren of te weigeren.' % prof.employee_id.name,
            )

    def action_accept(self):
        for invite in self:
            if invite.state != 'pending':
                raise UserError("Deze uitnodiging is al beantwoord.")
            invite.state = 'accepted'
            invite._feedback_activity('geaccepteerd')

    def action_reject(self):
        for invite in self:
            if invite.state != 'pending':
                raise UserError("Deze uitnodiging is al beantwoord.")
            invite.state = 'rejected'
            invite._feedback_activity('geweigerd')

    def _feedback_activity(self, result):
        """Mark the scheduled activity as done when the invite is answered."""
        for invite in self:
            if not invite.employee_id.user_id:
                continue
            prof = invite.professionalisering_id
            activities = prof.activity_ids.filtered(
                lambda a: a.user_id == invite.employee_id.user_id
                and 'Uitnodiging professionalisering' in (a.summary or '')
            )
            activities.action_done()


class ProfessionaliseringKostenLine(models.Model):
    _name = 'professionalisering.kosten.line'
    _description = 'Professionalisering Kostenlijn'

    professionalisering_id = fields.Many2one(
        'professionalisering.record', string='Professionalisering',
        required=True, ondelete='cascade',
    )
    omschrijving = fields.Char(string='Omschrijving', required=True)
    bedrag = fields.Monetary(string='Bedrag', currency_field='currency_id')
    currency_id = fields.Many2one(related='professionalisering_id.currency_id')
    is_auto = fields.Boolean(string='Automatisch', default=False)

    def unlink(self):
        if not self.env.context.get('force_unlink_auto') and self.filtered('is_auto'):
            raise UserError("Automatische kostenlijnen (bv. Verzekering) kunnen niet verwijderd worden.")
        return super().unlink()


class ProfessionaliseringDateLine(models.Model):
    _name = 'professionalisering.date.line'
    _description = 'Professionalisering Datum'
    _order = 'date'

    professionalisering_id = fields.Many2one('professionalisering.record', required=True, ondelete='cascade')
    professionalisering_titel = fields.Char(related='professionalisering_id.titel', string='Professionalisering')
    date = fields.Date(string='Datum', required=True)
    cost = fields.Float(string='Kost (€)')
