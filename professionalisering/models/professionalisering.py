from odoo import models, fields, api
from odoo.exceptions import UserError


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
    datum = fields.Date(string='Datum', required=True)
    cost = fields.Float(string='Kost (€)')
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                sequence = self.env['ir.sequence'].next_by_code('professionalisering.record')
                if not sequence:
                    raise UserError("Sequentie 'professionalisering.record' niet gevonden.")
                vals['name'] = sequence
        return super().create(vals_list)

    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Alleen conceptaanvragen kunnen ingediend worden.")
            record.state = 'submitted'
        self._send_notification('professionalisering.email_template_notify_directie')

    def action_approve(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError("Alleen ingediende aanvragen kunnen goedgekeurd worden.")
            record.state = 'approved'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification('professionalisering.email_template_notify_employee_approved')

    def action_reject(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError("Alleen ingediende aanvragen kunnen afgekeurd worden.")
            record.state = 'rejected'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification('professionalisering.email_template_notify_employee_rejected')

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

    def _send_notification(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for record in self:
                template.send_mail(record.id, force_send=True)
