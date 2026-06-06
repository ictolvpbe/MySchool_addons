from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MyschoolServerDataLocation(models.Model):
    """Waar leeft een data-domein voor een gegeven server (SRVMGR-4).

    Per server en per data-domein: staat de data **lokaal** of wordt ze
    **via API bij een bronserver** opgehaald (privacy-by-design). Sluit aan op
    de master/slave-replicatie (myschool_sync).
    """

    _name = 'myschool.server.data.location'
    _description = 'Server Data Location'
    _order = 'server_id, domain_id'

    server_id = fields.Many2one(
        'myschool.server', string='Server', required=True,
        ondelete='cascade', index=True)
    domain_id = fields.Many2one(
        'myschool.data.domain', string='Data Domain', required=True,
        ondelete='restrict', index=True)
    is_pii = fields.Boolean(related='domain_id.is_pii', string='PII', store=True)

    location = fields.Selection([
        ('local', 'Local'),
        ('remote', 'Remote via API'),
    ], string='Location', required=True, default='local')

    source_server_id = fields.Many2one(
        'myschool.server', string='Source Server',
        ondelete='restrict',
        help='Server waar deze data leeft en vanwaar ze via API opgehaald wordt '
             '(verplicht bij "Remote via API").')
    endpoint = fields.Char(
        string='Endpoint',
        help='Optionele override van het API-endpoint van de bronserver.')
    notes = fields.Char(string='Notes')

    _server_domain_unique = models.Constraint(
        'UNIQUE(server_id, domain_id)',
        'Each data domain can be configured only once per server.')

    @api.constrains('location', 'source_server_id', 'server_id')
    def _check_remote_source(self):
        for rec in self:
            if rec.location == 'remote':
                if not rec.source_server_id:
                    raise ValidationError(_(
                        "Een remote data-locatie vereist een bronserver."))
                if rec.source_server_id == rec.server_id:
                    raise ValidationError(_(
                        "De bronserver moet verschillen van de server zelf."))

    @api.onchange('location')
    def _onchange_location(self):
        if self.location == 'local':
            self.source_server_id = False
            self.endpoint = False
