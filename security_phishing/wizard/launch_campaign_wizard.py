import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PhishingLaunchWizard(models.TransientModel):
    _name = 'phishing.launch.wizard'
    _description = 'Phishing Campagne Starten Wizard'

    campaign_id = fields.Many2one(
        'phishing.campaign', string='Campagne',
        required=True, ondelete='cascade',
    )
    user_ids = fields.Many2many(
        'res.users', string='Gebruikers',
        domain=[('share', '=', False)],
        help='Selecteer de gebruikers die als doelwit worden toegevoegd.',
    )
    send_immediately = fields.Boolean(
        string='Direct Versturen', default=False,
        help='Verstuur de phishing e-mails direct na het starten van de campagne.',
    )

    def action_launch(self):
        """Voeg geselecteerde gebruikers als doelwitten toe en start de campagne."""
        self.ensure_one()

        if not self.user_ids:
            raise UserError(_('Selecteer ten minste één gebruiker.'))

        campaign = self.campaign_id
        Target = self.env['phishing.target']

        existing_partners = campaign.target_ids.mapped('partner_id')
        new_targets = []

        for user in self.user_ids:
            if user.partner_id not in existing_partners:
                new_targets.append({
                    'campaign_id': campaign.id,
                    'partner_id': user.partner_id.id,
                    'user_id': user.id,
                })

        if new_targets:
            Target.create(new_targets)

        if campaign.state == 'draft':
            campaign.action_start()

        if self.send_immediately:
            campaign.action_send_emails()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'phishing.campaign',
            'res_id': campaign.id,
            'view_mode': 'form',
            'target': 'current',
        }
