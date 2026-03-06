from odoo import models, fields, api
from odoo.exceptions import UserError


class AanvraagBuitenschoolseActiviteit(models.Model):
    _name = 'aanvraag_buitenschoolse_activiteit.record'
    _description = 'Aanvraag Buitenschoolse Activiteit'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referentie',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
    titel = fields.Char(string='Titel activiteit', required=True)
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
    datum = fields.Date(string='Datum activiteit', required=True)
    datum_display = fields.Char(string='Datum', compute='_compute_datum_display')
    bestemming = fields.Char(string='Bestemming', required=True)
    aantal_leerlingen = fields.Integer(string='Aantal leerlingen')
    cost = fields.Float(string='Geschatte kost (€)')
    state = fields.Selection([
        ('draft', 'Concept'),
        ('submitted', 'Ingediend'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('done', 'Afgerond'),
    ], string='Status', default='draft', tracking=True)
    rejection_reason = fields.Text(string='Reden voor afkeuring')
    assigned_to = fields.Many2one(
        'hr.employee',
        string='Toegewezen aan',
        tracking=True,
        domain=lambda self: [('user_id', 'in',
            self.env.ref('aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_directie').all_user_ids.ids
        )],
    )
    directie_id = fields.Many2one(
        'hr.employee',
        string='Beoordeeld door',
        readonly=True,
    )
    reservatie_done = fields.Boolean(string='Reservatie bevestigd', default=False)
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

    @api.depends('datum')
    def _compute_datum_display(self):
        for record in self:
            record.datum_display = record.datum.strftime('%d %b %Y') if record.datum else ''

    @api.depends('employee_id')
    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = record.employee_id and record.employee_id.user_id == self.env.user

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                sequence = self.env['ir.sequence'].next_by_code(
                    'aanvraag_buitenschoolse_activiteit.record')
                if not sequence:
                    raise UserError(
                        "Sequentie 'aanvraag_buitenschoolse_activiteit.record' niet gevonden.")
                vals['name'] = sequence
        return super().create(vals_list)

    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Alleen conceptaanvragen kunnen ingediend worden.")
            record.state = 'submitted'
        self._send_notification(
            'aanvraag_buitenschoolse_activiteit.email_template_notify_directie')

    def action_approve(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError("Alleen ingediende aanvragen kunnen goedgekeurd worden.")
            record.state = 'approved'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification(
            'aanvraag_buitenschoolse_activiteit.email_template_notify_employee_approved')

    def action_reject(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError("Alleen ingediende aanvragen kunnen afgekeurd worden.")
            record.state = 'rejected'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification(
            'aanvraag_buitenschoolse_activiteit.email_template_notify_employee_rejected')

    def action_confirm_reservatie(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(
                    "Reservatie kan alleen bevestigd worden voor goedgekeurde aanvragen.")
            record.reservatie_done = True
            record._check_done()

    def action_confirm_payment(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(
                    "Betaling kan alleen bevestigd worden voor goedgekeurde aanvragen.")
            record.payment_done = True
            record._check_done()

    def action_reset_draft(self):
        for record in self:
            if record.state != 'rejected':
                raise UserError(
                    "Alleen afgekeurde aanvragen kunnen opnieuw ingediend worden.")
            record.state = 'draft'
            record.rejection_reason = False
            record.directie_id = False

    def action_confirm_replacement(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(
                    "Vervanging kan alleen ingepland worden voor goedgekeurde aanvragen.")
            if not record.replacement_id:
                raise UserError(
                    "Selecteer eerst een vervanger voordat u de vervanging bevestigt.")
            record.replacement_done = True
            record._check_done()

    def _check_done(self):
        for record in self:
            if record.reservatie_done and record.payment_done and record.replacement_done:
                record.state = 'done'

    def action_delete(self):
        self.unlink()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def _send_notification(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for record in self:
                template.send_mail(record.id, force_send=True)
