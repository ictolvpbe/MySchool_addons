# -*- coding: utf-8 -*-
"""
Sync Target
============
Registry of slave servers that the master syncs data to.
Each target has a URL, API key, per-model toggles, and optional school filter.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from . import sync_model_registry
import json
import logging

_logger = logging.getLogger(__name__)


class SyncTarget(models.Model):
    _name = 'sync.target'
    _description = 'Sync Target Server'
    _order = 'name'

    name = fields.Char(string='Name', required=True, index=True)
    url = fields.Char(string='URL', required=True, help='Base URL of the slave instance (e.g. https://slave.example.com)')
    api_key = fields.Char(string='API Key', required=True, groups='base.group_system')
    is_active = fields.Boolean(string='Active', default=True)

    # Per-model toggles
    sync_person = fields.Boolean(string='Sync Persons', default=True)
    sync_org = fields.Boolean(string='Sync Organizations', default=True)
    sync_role = fields.Boolean(string='Sync Roles', default=True)
    sync_proprelation = fields.Boolean(string='Sync PropRelations', default=True)
    sync_period = fields.Boolean(string='Sync Periods', default=True)
    sync_types = fields.Boolean(string='Sync Type Models', default=True)

    # School filter
    school_org_ids = fields.Many2many(
        'myschool.org',
        'sync_target_school_rel',
        'target_id', 'org_id',
        string='School Filter',
        help='Only sync data for these schools. Leave empty to sync all.',
    )

    # Status
    last_sync_date = fields.Datetime(string='Last Successful Sync', readonly=True)
    last_error = fields.Text(string='Last Error', readonly=True)
    consecutive_errors = fields.Integer(string='Consecutive Errors', default=0, readonly=True)

    _name_unique = models.Constraint('UNIQUE(name)', 'Target name must be unique!')
    _url_unique = models.Constraint('UNIQUE(url)', 'Target URL must be unique!')

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_test_connection(self):
        """Test connectivity to the slave by calling /myschool_sync/ping."""
        self.ensure_one()
        dispatcher = self.env['sync.dispatcher']
        try:
            result = dispatcher.ping_target(self)
            if result.get('success'):
                self.write({
                    'last_error': False,
                    'consecutive_errors': 0,
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection OK'),
                        'message': _('Successfully connected to %s') % self.name,
                        'type': 'success',
                    },
                }
            else:
                error = result.get('error', 'Unknown error')
                self.write({'last_error': error})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Failed'),
                        'message': error,
                        'type': 'danger',
                    },
                }
        except Exception as e:
            self.write({'last_error': str(e)})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': str(e),
                    'type': 'danger',
                },
            }

    def action_trigger_full_sync(self):
        """Create API_*_SYNC betasks for all records of all enabled models."""
        self.ensure_one()
        if not self.is_active:
            raise UserError(_('Cannot sync to an inactive target.'))

        betask_service = self.env['myschool.betask.service']
        serializer = self.env['sync.serializer']
        created = 0

        for entry in sync_model_registry.get_models_sorted_by_priority():
            flag = entry['target_flag']
            if not getattr(self, flag, False):
                continue

            Model = self.env[entry['model']].sudo().with_context(active_test=False)
            records = Model.search([])

            for record in records:
                payload = serializer.serialize_record(record, entry)
                if not payload:
                    continue

                data = json.dumps({
                    'sync_target_id': self.id,
                    'payloads': [payload],
                })
                betask_service.create_task(
                    'API', entry['betask_object'], 'SYNC',
                    data=data,
                )
                created += 1

        _logger.info('Full sync: created %d betasks for target %s', created, self.name)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Full Sync Triggered'),
                'message': _('%d sync tasks created for %s') % (created, self.name),
                'type': 'success',
            },
        }

    def action_view_sync_logs(self):
        """Open sync logs filtered by this target."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Logs: %s') % self.name,
            'res_model': 'sync.log',
            'view_mode': 'list,form',
            'domain': [('sync_target_id', '=', self.id)],
            'context': {'default_sync_target_id': self.id},
        }
