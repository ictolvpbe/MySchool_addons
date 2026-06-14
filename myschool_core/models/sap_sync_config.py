# -*- coding: utf-8 -*-
"""
SAP-sync Safeguard Configuration
================================

Neutral, connector-agnostic configuration for the SAP-sync safeguard
(threshold-check that suspends a sync-run when too large a fraction of a
population changes). Previously these thresholds lived on
``myschool.informat.service.config``, but the safeguard belongs to the
SAP-sync orchestration in the kernel — not to the Informat connector.
Splitting them out lets the Informat integration move to its own
edition-plugin while the safeguard stays neutral in core.
"""

from odoo import api, fields, models


class SapSyncConfig(models.Model):
    """Singleton config for the SAP-sync safeguard thresholds."""

    _name = 'myschool.sap.sync.config'
    _description = 'SAP-sync Safeguard Configuration'
    _rec_name = 'name'

    name = fields.Char(
        string='Configuration Name',
        required=True,
        default='Default Configuration',
    )

    active = fields.Boolean(string='Active', default=True)

    # =====================================================================
    # Safeguard thresholds
    # =====================================================================
    # Bij overschrijden van het ingestelde % per object_type schort de
    # service de sync op (state=awaiting_approval) en stuurt een mail
    # naar de admins. Default = 20%. Werkt enkel als ``safeguard_enabled``.

    safeguard_enabled = fields.Boolean(
        string='Safeguard ingeschakeld',
        default=True,
        help='Als uitgeschakeld: drempel-check wordt overgeslagen en '
             'syncs committeren zoals voorheen (geen mail-alarm).'
    )

    threshold_person_pct = fields.Float(
        string='Drempel PERSON (%)',
        default=20.0,
        help='Maximaal toegestaan % wijzigende personen voor een '
             'automatische commit. Boven dit % wacht de run op '
             'expliciete goedkeuring.'
    )
    threshold_org_pct = fields.Float(
        string='Drempel ORG (%)',
        default=20.0,
    )
    threshold_orggroup_pct = fields.Float(
        string='Drempel ORGGROUP (%)',
        default=20.0,
        help='Drempel voor org-records van type PERSONGROUP (klasgroepen e.d.).'
    )
    threshold_proprelation_pct = fields.Float(
        string='Drempel PROPRELATION (%)',
        default=20.0,
    )

    safeguard_min_changes = fields.Integer(
        string='Min. wijzigingen om alarm te triggeren',
        default=5,
        help='Voorkomt valse alarmen op kleine populaties: drempel '
             'wordt enkel toegepast vanaf dit absolute aantal mutaties.'
    )

    @api.model
    def get_config(self):
        """Get the active configuration record. Creates default if none exists."""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            config = self.create({'name': 'Default Configuration'})
        return config
