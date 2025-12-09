from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class NascholingAanvraag(models.Model):
    _name = 'nascholing.aanvraag'
    _description = 'Nascholingsaanvraag'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Referentie', required=True, copy=False, readonly=True, default=lambda self: ('New'))
    description = fields.Text(string='Beschrijving', required=True)
    start_date = fields.Date(string='Startdatum', required=True)
    end_date = fields.Date(string='Einddatum', required=True)
    cost = fields.Float(string='Kost (€)', required=True)
    state = fields.Selection([
        ('draft', 'Concept'),
        ('submitted', 'Ingediend'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('planned', 'Ingeplanned'),
    ], string='Status', default='draft', tracking=True)
    reason = fields.Text(string='Reden voor afkeuring')
    #teacher_id = fields.Many2one('hr.employee', string='Leerkracht', required=True, default=lambda self: self.env.user.employee_ids[:1])
    teacher_id = fields.Many2one('hr.employee', string='Leerkracht', required=True,
                                 default=lambda self: self.env.user.employee_ids[:1])
    director_id = fields.Many2one('hr.employee', string='Directie', readonly=True)

    @api.model
    def create(self, vals):
        # Haal het volgende sequentienummer op
        sequence = self.env['ir.sequence'].next_by_code('nascholing.aanvraag')
        if not sequence:
            raise UserError("Sequentie 'nascholing.aanvraag' niet gevonden. Controleer de sequentie-definitie.")
        vals[0]['name'] = sequence
        vals[0]['state'] = 'draft'
        return super(NascholingAanvraag, self).create(vals)

    def submit_request(self):
        self.state = 'submitted'
        self._send_notification_to_directie()

    def approve_request(self):
        self.state = 'approved'
        self._send_notification_to_teacher()

    def reject_request(self):
        self.state = 'rejected'
        self._send_notification_to_teacher()

    def _send_notification_to_directie(self):
        template = self.env.ref('nascholing_workflow.email_template_notify_directie')
        for aanvraag in self:
            template.send_mail(aanvraag.id, force_send=True)

    def _send_notification_to_teacher(self):
        template = self.env.ref('nascholing_workflow.email_template_notify_teacher')
        for aanvraag in self:
            template.send_mail(aanvraag.id, force_send=True)

