import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Clear asset cache so the new theme takes effect immediately."""
    env['ir.attachment'].search([
        ('url', 'like', '/web/assets/%'),
    ]).unlink()
    _logger.info('MySchool Theme: asset cache cleared.')
