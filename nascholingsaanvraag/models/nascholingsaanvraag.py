from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class NascholingsaanvraagRecord(models.Model):
    _name = 'nascholingsaanvraag.record'
    _description = 'Nascholingsaanvraag'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referentie',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
    titel = fields.Char(string='Titel nascholing', required=True)
    description = fields.Text(string='Beschrijving')
    employee_id = fields.Many2one(
        'hr.employee',
        string='Medewerker',
        required=True,
        default=lambda self: self.env.user.employee_ids[:1],
    )
    start_date = fields.Date(string='Startdatum', required=True)
    end_date = fields.Date(string='Einddatum')
    verschillende_dagen = fields.Boolean(string='Verschillende dagen', default=False)
    date_line_ids = fields.One2many('nascholingsaanvraag.date.line', 'aanvraag_id', string='Datums')
    dates_display = fields.Html(string='Datums', compute='_compute_dates_display', sanitize=False)
    cost = fields.Float(string='Kost (€)')
    total_cost = fields.Float(string='Totale kost (€)', compute='_compute_total_cost')
    state = fields.Selection([
        ('draft', 'Concept'),
        ('submitted', 'Ingediend'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('done', 'Afgerond'),
    ], string='Status', default='draft', tracking=True)
    rejection_reason = fields.Text(string='Reden voor afkeuring')
    directie_id = fields.Many2one(
        'hr.employee',
        string='Beoordeeld door',
        readonly=True,
    )
    payment_done = fields.Boolean(string='Betaling bevestigd', default=False)
    replacement_done = fields.Boolean(string='Vervanging ingepland', default=False)

    @api.depends('verschillende_dagen', 'start_date', 'end_date', 'date_line_ids.date', 'date_line_ids.cost')
    def _compute_dates_display(self):
        for record in self:
            if record.verschillende_dagen:
                all_dates = []
                if record.start_date:
                    all_dates.append('%s &nbsp;-&nbsp; €%.2f' % (
                        record.start_date.strftime('%d/%m/%Y'), record.cost or 0,
                    ))
                for line in record.date_line_ids.sorted('date'):
                    if line.date:
                        all_dates.append('%s &nbsp;-&nbsp; €%.2f' % (
                            line.date.strftime('%d/%m/%Y'), line.cost or 0,
                        ))
                record.dates_display = '<br/>'.join(all_dates)
            elif record.start_date and record.end_date:
                record.dates_display = '%s → %s' % (
                    record.start_date.strftime('%d/%m/%Y'),
                    record.end_date.strftime('%d/%m/%Y'),
                )
            elif record.start_date:
                record.dates_display = record.start_date.strftime('%d/%m/%Y')
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
                sequence = self.env['ir.sequence'].next_by_code('nascholingsaanvraag.record')
                if not sequence:
                    raise UserError("Sequentie 'nascholingsaanvraag.record' niet gevonden.")
                vals['name'] = sequence
        return super().create(vals_list)

    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Alleen conceptaanvragen kunnen ingediend worden.")
            record.state = 'submitted'
        self._send_notification('nascholingsaanvraag.email_template_notify_directie')

    def action_approve(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError("Alleen ingediende aanvragen kunnen goedgekeurd worden.")
            record.state = 'approved'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification('nascholingsaanvraag.email_template_notify_employee_approved')

    def action_reject(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError("Alleen ingediende aanvragen kunnen afgekeurd worden.")
            record.state = 'rejected'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification('nascholingsaanvraag.email_template_notify_employee_rejected')

    def action_confirm_payment(self):
        for record in self:
            if record.state != 'approved':
                raise UserError("Betaling kan alleen bevestigd worden voor goedgekeurde aanvragen.")
            record.payment_done = True
            record._check_done()

    def action_confirm_replacement(self):
        for record in self:
            if record.state != 'approved':
                raise UserError("Vervanging kan alleen ingepland worden voor goedgekeurde aanvragen.")
            record.replacement_done = True
            record._check_done()

    def action_reset_draft(self):
        for record in self:
            if record.state != 'rejected':
                raise UserError("Alleen afgekeurde aanvragen kunnen opnieuw ingediend worden.")
            record.state = 'draft'
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

    def _send_notification(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for record in self:
                template.send_mail(record.id, force_send=True)


class NascholingsaanvraagDateLine(models.Model):
    _name = 'nascholingsaanvraag.date.line'
    _description = 'Nascholingsaanvraag Datum'
    _order = 'date'

    aanvraag_id = fields.Many2one('nascholingsaanvraag.record', required=True, ondelete='cascade')
    aanvraag_titel = fields.Char(related='aanvraag_id.titel', string='Nascholing')
    date = fields.Date(string='Datum', required=True)
    cost = fields.Float(string='Kost (€)')
