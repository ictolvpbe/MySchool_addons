import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class PhishingResult(models.Model):
    _name = 'phishing.result'
    _description = 'Phishing Resultaat'
    _order = 'campaign_id'
    _rec_name = 'campaign_id'

    campaign_id = fields.Many2one(
        'phishing.campaign', string='Campagne',
        required=True, ondelete='cascade', index=True,
    )
    sent_count = fields.Integer(string='Verzonden')
    clicked_count = fields.Integer(string='Geklikt')
    reported_count = fields.Integer(string='Gerapporteerd')
    credentials_count = fields.Integer(string='Inloggegevens Ingevoerd')
    click_rate = fields.Float(string='Klikpercentage (%)')
    report_rate = fields.Float(string='Rapportagepercentage (%)')

    _unique_campaign = models.Constraint(
        'UNIQUE(campaign_id)',
        'Er kan slechts één resultaat per campagne bestaan.',
    )
