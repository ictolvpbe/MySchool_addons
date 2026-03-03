from odoo import models, fields, api
from odoo.exceptions import UserError


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
    end_date = fields.Date(string='Einddatum', required=True)
    cost = fields.Float(string='Kost (€)')
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

    def _send_notification(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for record in self:
                template.send_mail(record.id, force_send=True)
