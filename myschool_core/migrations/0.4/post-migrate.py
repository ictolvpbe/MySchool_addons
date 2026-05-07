import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-migrate 0.4: verwijder de gedeprecieerde `myschool_bus_seater`
    module als die nog geinstalleerd is. Sinds OLVP de busverdeling per
    uitstap via `activiteiten.bus` afhandelt, is bus_seater niet meer nodig.
    De module is in zijn manifest op installable=False gezet, maar bestaande
    installs blijven anders zichtbaar in de Apps-drawer.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Module = env['ir.module.module']
    bus_seater = Module.search([('name', '=', 'myschool_bus_seater')], limit=1)
    if not bus_seater:
        _logger.info('[myschool_core 0.4] bus_seater module not present, skipping')
        return
    if bus_seater.state in ('installed', 'to upgrade', 'to install'):
        _logger.info('[myschool_core 0.4] marking deprecated myschool_bus_seater module for uninstall')
        try:
            # button_uninstall markeert de module als 'to remove' — Odoo voert
            # de daadwerkelijke uninstall pas uit aan het einde van de huidige
            # upgrade-cyclus. We vermijden zo een mid-upgrade registry-reload
            # die `button_immediate_uninstall` zou triggeren.
            bus_seater.button_uninstall()
        except Exception as e:
            _logger.warning(
                '[myschool_core 0.4] failed to mark bus_seater for uninstall: %s. '
                'Manual uninstall via Apps required.', e,
            )
    else:
        _logger.info(
            '[myschool_core 0.4] bus_seater state=%s — niets te doen',
            bus_seater.state,
        )
