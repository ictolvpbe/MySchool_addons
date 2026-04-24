import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info('[professionalisering 1.1] post-migrate called, installed_version=%r', version)
    env = api.Environment(cr, SUPERUSER_ID, {})
    existing = env['ir.sequence'].sudo().search(
        [('code', '=', 'professionalisering.record')], limit=1,
    )
    if existing:
        _logger.info('[professionalisering 1.1] sequence already exists, nothing to do')
        return
    env['ir.sequence'].sudo().create({
        'name': 'Professionalisering',
        'code': 'professionalisering.record',
        'prefix': 'PR-',
        'padding': 5,
        'number_next': 1,
        'number_increment': 1,
        'implementation': 'standard',
    })
    _logger.info('[professionalisering 1.1] sequence created')
