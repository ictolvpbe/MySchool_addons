import logging

from odoo import models, fields, _

_logger = logging.getLogger(__name__)


class PhishingTemplate(models.Model):
    _name = 'phishing.template'
    _description = 'Phishing E-mail Sjabloon'
    _order = 'name'

    name = fields.Char(string='Naam', required=True)
    subject = fields.Char(string='Onderwerp', required=True)
    sender_name = fields.Char(string='Afzendernaam', required=True)
    sender_address = fields.Char(string='Afzenderadres', required=True)
    body_html = fields.Html(
        string='E-mail Inhoud',
        sanitize=False,
        help='HTML inhoud van de phishing e-mail. '
             'Gebruik {{tracking_pixel}} voor de trackingpixel, '
             '{{report_link}} voor de rapporteerlink en '
             '{{landing_link}} voor de nep-loginpagina.',
    )
    campaign_ids = fields.One2many(
        'phishing.campaign', 'template_id', string='Campagnes',
    )
    campaign_count = fields.Integer(
        string='Aantal Campagnes', compute='_compute_campaign_count',
    )

    def _compute_campaign_count(self):
        for record in self:
            record.campaign_count = len(record.campaign_ids)

    def action_view_campaigns(self):
        """Open campagnes die dit sjabloon gebruiken."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Campagnes'),
            'res_model': 'phishing.campaign',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
            'context': {'default_template_id': self.id},
        }
