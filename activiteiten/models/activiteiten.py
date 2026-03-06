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
    datetime = fields.Datetime(string='Datum en tijdstip')
    price = fields.Monetary(string='Geschatte kost', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency',
        string='Valuta',
        default=lambda self: self.env.company.currency_id,
    )
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
    verzekering_done = fields.Boolean(string='Verzekering geregeld', default=False)
    vervanging_done = fields.Boolean(string='Vervanging ingepland', default=False)
    vervanger_id = fields.Many2one('res.users', string='Vervanger', tracking=True)
    rejection_reason = fields.Text(string='Reden voor afkeuring')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'De referentie moet uniek zijn.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                # Sync sequence with highest existing record
                last_record = self.search(
                    [('name', 'like', 'ACT-%')],
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
                    raise UserError(
                        "Sequentie 'activiteiten.record' niet gevonden.")
                if seq.number_next_actual <= last_number:
                    seq.sudo().number_next_actual = last_number + 1
                # ir.sequence is concurrency-safe (uses DB lock)
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'activiteiten.record')
        return super().create(vals_list)

    # --- Personeelslid actions ---

    def action_select_binnenschools(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Alleen conceptaanvragen kunnen geselecteerd worden.")
            record.activity_type = 'binnenschools'
            record.state = 'form_invullen'

    def action_select_buitenschools(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Alleen conceptaanvragen kunnen geselecteerd worden.")
            record.activity_type = 'buitenschools'
            record.state = 'form_invullen'

    def action_submit_form(self):
        for record in self:
            if record.state not in ('form_invullen', 'bus_refused'):
                raise UserError("Het formulier kan alleen vanuit de invulfase ingediend worden.")
            if not record.titel:
                raise UserError("Vul een titel in.")
            if not record.datetime:
                raise UserError("Vul een datum en tijdstip in.")
            if record.bus_nodig:
                record.state = 'bus_check'
            else:
                record.state = 'pending_approval'
        self._send_notification(
            'activiteiten.email_template_notify_directie')

    # --- Aankoop actions ---

    def action_bus_approved(self):
        for record in self:
            if record.state != 'bus_check':
                raise UserError("Bus controle is niet van toepassing.")
            record.bus_available = True
            record.state = 'pending_approval'
        self._send_notification(
            'activiteiten.email_template_notify_directie')

    def action_bus_refused(self):
        for record in self:
            if record.state != 'bus_check':
                raise UserError("Bus controle is niet van toepassing.")
            record.bus_available = False
            record.state = 'bus_refused'
        self._send_notification(
            'activiteiten.email_template_bus_refused')

    # --- Directie actions ---

    def action_approve(self):
        for record in self:
            if record.state != 'pending_approval':
                raise UserError("Alleen aanvragen in afwachting kunnen goedgekeurd worden.")
            record.state = 's_code'
        self._send_notification(
            'activiteiten.email_template_approved')
        self._schedule_boekhouding_activity()
        self._schedule_owner_approved_activity()

    def action_reject(self):
        for record in self:
            if record.state != 'pending_approval':
                raise UserError("Alleen aanvragen in afwachting kunnen afgekeurd worden.")
            record.state = 'rejected'
        self._send_notification(
            'activiteiten.email_template_rejected')

    # --- Boekhouding actions ---

    def action_confirm_s_code(self):
        for record in self:
            if record.state != 's_code':
                raise UserError("S-Code kan alleen in de S-Code fase bevestigd worden.")
            if not record.s_code_name:
                raise UserError("Vul eerst de S-Code in.")
            if not record.s_code_price:
                raise UserError("Vul eerst het S-Code bedrag in.")
            record.state = 'vervanging'
        self._schedule_vervangingen_activity()

    def action_verzekering_done(self):
        for record in self:
            if record.state not in ('s_code', 'vervanging'):
                raise UserError("Verzekering kan alleen bij S-Code of vervanging afgehandeld worden.")
            record.verzekering_done = True
            record._check_done()

    # --- Vervangingen actions ---

    def action_plan_vervanging(self):
        for record in self:
            if record.state != 'vervanging':
                raise UserError("Vervanging kan alleen in de vervangingsfase ingepland worden.")
            if not record.vervanger_id:
                raise UserError("Selecteer eerst een vervanger voordat u de vervanging bevestigt.")
            record.vervanging_done = True
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
            if record.verzekering_done and record.vervanging_done:
                record.state = 'done'

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
                    summary='Vervanging inplannen',
                    note=f'De S-Code voor activiteit "{record.titel}" is ingevuld. Gelieve een vervanger te kiezen.',
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

    def _send_notification(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for record in self:
                template.send_mail(record.id, force_send=True)
