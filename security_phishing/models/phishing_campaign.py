import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CAMPAIGN_STATES = [
    ('draft', 'Concept'),
    ('running', 'Actief'),
    ('completed', 'Afgerond'),
]


class PhishingCampaign(models.Model):
    _name = 'phishing.campaign'
    _description = 'Phishing Campagne'
    _order = 'date_start desc, name'

    name = fields.Char(string='Naam', required=True)
    description = fields.Text(string='Omschrijving')
    state = fields.Selection(
        CAMPAIGN_STATES, string='Status', default='draft',
        required=True,
    )
    date_start = fields.Date(string='Startdatum')
    date_end = fields.Date(string='Einddatum')
    responsible_id = fields.Many2one(
        'res.users', string='Verantwoordelijke',
        default=lambda self: self.env.uid, required=True,
        ondelete='restrict',
    )
    template_id = fields.Many2one(
        'phishing.template', string='E-mail Sjabloon',
        required=True, ondelete='restrict',
    )
    target_ids = fields.One2many(
        'phishing.target', 'campaign_id', string='Doelwitten',
    )
    result_ids = fields.One2many(
        'phishing.result', 'campaign_id', string='Resultaten',
    )

    # Computed stats
    target_count = fields.Integer(
        string='Aantal Doelwitten', compute='_compute_stats', store=True,
    )
    sent_count = fields.Integer(
        string='Verzonden', compute='_compute_stats', store=True,
    )
    clicked_count = fields.Integer(
        string='Geklikt', compute='_compute_stats', store=True,
    )
    reported_count = fields.Integer(
        string='Gerapporteerd', compute='_compute_stats', store=True,
    )
    credentials_count = fields.Integer(
        string='Inloggegevens Ingevoerd', compute='_compute_stats', store=True,
    )
    click_rate = fields.Float(
        string='Klikpercentage (%)', compute='_compute_stats', store=True,
    )
    report_rate = fields.Float(
        string='Rapportagepercentage (%)', compute='_compute_stats', store=True,
    )

    @api.depends(
        'target_ids', 'target_ids.state',
    )
    def _compute_stats(self):
        for campaign in self:
            targets = campaign.target_ids
            total = len(targets)
            sent = len(targets.filtered(lambda t: t.state != 'pending'))
            clicked = len(targets.filtered(lambda t: t.state in ('clicked', 'credentials_entered')))
            reported = len(targets.filtered(lambda t: t.reported))
            credentials = len(targets.filtered(lambda t: t.state == 'credentials_entered'))

            campaign.target_count = total
            campaign.sent_count = sent
            campaign.clicked_count = clicked
            campaign.reported_count = reported
            campaign.credentials_count = credentials
            campaign.click_rate = (clicked / sent * 100) if sent else 0.0
            campaign.report_rate = (reported / sent * 100) if sent else 0.0

    def action_start(self):
        """Start de campagne."""
        for campaign in self:
            if campaign.state != 'draft':
                raise UserError(_('Alleen conceptcampagnes kunnen gestart worden.'))
            if not campaign.target_ids:
                raise UserError(_('Voeg eerst doelwitten toe voordat u de campagne start.'))
            campaign.state = 'running'

    def action_complete(self):
        """Rond de campagne af."""
        for campaign in self:
            if campaign.state != 'running':
                raise UserError(_('Alleen actieve campagnes kunnen afgerond worden.'))
            campaign.state = 'completed'
            # Create or update aggregated result
            campaign._update_result()

    def action_reset_to_draft(self):
        """Zet de campagne terug naar concept."""
        for campaign in self:
            campaign.state = 'draft'

    def action_send_emails(self):
        """Verstuur phishing e-mails naar alle doelwitten."""
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_('De campagne moet actief zijn om e-mails te versturen.'))

        pending_targets = self.target_ids.filtered(lambda t: t.state == 'pending')
        if not pending_targets:
            raise UserError(_('Er zijn geen doelwitten met status "Wachtend" om te versturen.'))

        pending_targets._send_phishing_email()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('E-mails Verstuurd'),
                'message': _('%d e-mails zijn verstuurd.') % len(pending_targets),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_targets(self):
        """Open doelwitten van deze campagne."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Doelwitten'),
            'res_model': 'phishing.target',
            'view_mode': 'list,form',
            'domain': [('campaign_id', '=', self.id)],
            'context': {'default_campaign_id': self.id},
        }

    def action_launch_wizard(self):
        """Open de wizard om doelwitten te selecteren en de campagne te starten."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Campagne Starten'),
            'res_model': 'phishing.launch.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_campaign_id': self.id},
        }

    def _update_result(self):
        """Maak of werk het geaggregeerde resultaat bij."""
        Result = self.env['phishing.result']
        for campaign in self:
            result = Result.search([('campaign_id', '=', campaign.id)], limit=1)
            vals = campaign._prepare_result_vals()
            if result:
                result.write(vals)
            else:
                vals['campaign_id'] = campaign.id
                Result.create(vals)

    def _prepare_result_vals(self):
        """Bereid de resultaatwaarden voor."""
        self.ensure_one()
        return {
            'sent_count': self.sent_count,
            'clicked_count': self.clicked_count,
            'reported_count': self.reported_count,
            'credentials_count': self.credentials_count,
            'click_rate': self.click_rate,
            'report_rate': self.report_rate,
        }
