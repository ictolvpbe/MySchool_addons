import logging
import uuid

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TARGET_STATES = [
    ('pending', 'Wachtend'),
    ('sent', 'Verstuurd'),
    ('clicked', 'Geklikt'),
    ('credentials_entered', 'Inloggegevens Ingevoerd'),
]


class PhishingTarget(models.Model):
    _name = 'phishing.target'
    _description = 'Phishing Doelwit'
    _order = 'campaign_id, partner_id'
    _rec_name = 'display_name'

    campaign_id = fields.Many2one(
        'phishing.campaign', string='Campagne',
        required=True, ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner', string='Contactpersoon',
        required=True, ondelete='restrict',
    )
    user_id = fields.Many2one(
        'res.users', string='Gebruiker', ondelete='restrict',
    )
    token = fields.Char(
        string='Token', readonly=True, copy=False, index=True,
    )
    state = fields.Selection(
        TARGET_STATES, string='Status', default='pending',
        required=True, tracking=True,
    )
    reported = fields.Boolean(string='Gerapporteerd', default=False)
    date_sent = fields.Datetime(string='Verzenddatum', readonly=True)
    date_clicked = fields.Datetime(string='Klikdatum', readonly=True)
    date_reported = fields.Datetime(string='Rapportagedatum', readonly=True)
    date_credentials = fields.Datetime(
        string='Inloggegevens Datum', readonly=True,
    )
    email = fields.Char(
        string='E-mail', related='partner_id.email', readonly=True,
    )
    display_name = fields.Char(
        string='Naam', compute='_compute_display_name',
    )

    _sql_constraints = [
        (
            'unique_campaign_partner',
            'UNIQUE(campaign_id, partner_id)',
            'Een contactpersoon kan slechts één keer per campagne voorkomen.',
        ),
        (
            'unique_token',
            'UNIQUE(token)',
            'Token moet uniek zijn.',
        ),
    ]

    @api.depends('partner_id', 'campaign_id')
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.campaign_id:
                parts.append(record.campaign_id.name)
            if record.partner_id:
                parts.append(record.partner_id.name)
            record.display_name = ' - '.join(parts) if parts else ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('token'):
                vals['token'] = uuid.uuid4().hex
        return super().create(vals_list)

    def _send_phishing_email(self):
        """Verstuur de phishing e-mail naar dit doelwit."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        Mail = self.env['mail.mail']

        for target in self:
            if not target.partner_id.email:
                _logger.warning(
                    'Phishing target %s has no email, skipping.', target.id,
                )
                continue

            template = target.campaign_id.template_id
            tracking_url = f'{base_url}/phishing/track/{target.token}'
            report_url = f'{base_url}/phishing/report/{target.token}'
            landing_url = f'{base_url}/phishing/landing/{target.token}'

            tracking_pixel = (
                f'<img src="{tracking_url}" width="1" height="1" '
                f'style="display:none;" alt="" />'
            )

            body = template.body_html or ''
            body = body.replace('{{tracking_pixel}}', tracking_pixel)
            body = body.replace('{{report_link}}', report_url)
            body = body.replace('{{landing_link}}', landing_url)

            mail_values = {
                'subject': template.subject,
                'body_html': body,
                'email_from': f'{template.sender_name} <{template.sender_address}>',
                'email_to': target.partner_id.email,
                'auto_delete': False,
            }

            mail = Mail.sudo().create(mail_values)
            mail.send()

            target.write({
                'state': 'sent',
                'date_sent': fields.Datetime.now(),
            })

        _logger.info(
            'Sent phishing emails for %d targets.', len(self),
        )

    def action_record_click(self):
        """Registreer een klik voor dit doelwit."""
        now = fields.Datetime.now()
        for target in self:
            vals = {'date_clicked': now}
            if target.state == 'sent':
                vals['state'] = 'clicked'
            target.write(vals)

    def action_record_report(self):
        """Registreer een rapportage voor dit doelwit."""
        now = fields.Datetime.now()
        for target in self:
            target.write({
                'reported': True,
                'date_reported': now,
            })

    def action_record_credentials(self):
        """Registreer dat inloggegevens zijn ingevoerd."""
        now = fields.Datetime.now()
        for target in self:
            target.write({
                'state': 'credentials_entered',
                'date_credentials': now,
            })
