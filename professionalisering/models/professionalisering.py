from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


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
        ('binnenschools', 'Binnenschoolse'),
        ('buitenschools', 'Buitenschoolse'),
        ('extern', 'Externe'),
    ], string='Type', required=True)
    titel = fields.Char(string='Titel opleiding', required=True)
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
        default=lambda self: self.env.user.school_ids[:1],
    )
    is_owner = fields.Boolean(compute='_compute_is_owner')
    start_date = fields.Date(string='Startdatum', required=True)
    end_date = fields.Date(string='Einddatum')
    verschillende_dagen = fields.Boolean(string='Verschillende dagen', default=False)
    date_line_ids = fields.One2many('professionalisering.date.line', 'professionalisering_id', string='Datums')
    dates_display = fields.Html(string='Datums', compute='_compute_dates_display', sanitize=False)
    cost = fields.Float(string='Kost (€)')
    total_cost = fields.Float(string='Totale kost (€)', compute='_compute_total_cost')
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
        ('fill_in_form_binnenschoolse', 'Ingediend'),
        ('fill_in_form_buitenschoolse', 'Ingediend'),
        ('fill_in_form_externe', 'Ingediend'),
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
    replacement_id = fields.Many2one(
        'hr.employee',
        string='Vervanger',
        tracking=True,
    )
    replacement_done = fields.Boolean(string='Vervanging ingepland', default=False)
    priority = fields.Selection([
        ('0', 'Normaal'),
        ('1', 'Laag'),
        ('2', 'Hoog'),
        ('3', 'Urgent'),
    ], string='Prioriteit', default='0')

    @api.depends('employee_id')
    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = record.employee_id and record.employee_id.user_id == self.env.user

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
        return ['fill_in_form_binnenschoolse', 'fill_in_form_buitenschoolse', 'fill_in_form_externe']

    def action_submit(self):
        type_state_map = {
            'binnenschools': 'fill_in_form_binnenschoolse',
            'buitenschools': 'fill_in_form_buitenschoolse',
            'extern': 'fill_in_form_externe',
        }
        for record in self:
            if record.state != 'selection_of_form':
                raise UserError("Alleen conceptaanvragen kunnen ingediend worden.")
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
            record.payment_done = True
            record._check_done()

    def action_confirm_replacement(self):
        for record in self:
            if record.state != 'bevestiging':
                raise UserError("Vervanging kan alleen ingepland worden voor goedgekeurde aanvragen.")
            if not record.replacement_id:
                raise UserError("Selecteer eerst een vervanger voordat u de vervanging bevestigt.")
            record.replacement_done = True
            record._check_done()

    def action_reset_draft(self):
        for record in self:
            if record.state != 'weigering':
                raise UserError("Alleen afgekeurde aanvragen kunnen opnieuw ingediend worden.")
            record.state = 'selection_of_form'
            record.rejection_reason = False
            record.directie_id = False

    def _check_done(self):
        for record in self:
            if record.payment_done and record.replacement_done:
                record.state = 'done'

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

    def action_delete(self):
        self.unlink()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def _send_notification(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for record in self:
                template.send_mail(record.id, force_send=True)


class ProfessionaliseringDateLine(models.Model):
    _name = 'professionalisering.date.line'
    _description = 'Professionalisering Datum'
    _order = 'date'

    professionalisering_id = fields.Many2one('professionalisering.record', required=True, ondelete='cascade')
    professionalisering_titel = fields.Char(related='professionalisering_id.titel', string='Professionalisering')
    date = fields.Date(string='Datum', required=True)
    cost = fields.Float(string='Kost (€)')
