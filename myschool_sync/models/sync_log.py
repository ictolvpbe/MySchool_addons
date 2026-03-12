# -*- coding: utf-8 -*-
"""
Sync Log
========
Audit log for sync events on both master (outbound) and slave (inbound).
"""

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SyncLog(models.Model):
    _name = 'sync.log'
    _description = 'Sync Event Log'
    _order = 'create_date desc'

    name = fields.Char(string='Reference', readonly=True, default='/')
    model_name = fields.Char(string='Model', index=True)
    record_natural_key = fields.Char(string='Natural Key', help='JSON of the natural key')

    action = fields.Selection(
        [
            ('create', 'Create'),
            ('update', 'Update'),
            ('skip', 'Skip (no changes)'),
            ('deactivate', 'Deactivate'),
            ('error', 'Error'),
        ],
        string='Action',
        index=True,
    )
    direction = fields.Selection(
        [
            ('outbound', 'Outbound (master → slave)'),
            ('inbound', 'Inbound (slave ← master)'),
        ],
        string='Direction',
        index=True,
    )

    sync_target_id = fields.Many2one('sync.target', string='Target', index=True, ondelete='set null')
    payload = fields.Text(string='Payload')
    success = fields.Boolean(string='Success', default=True)
    error_message = fields.Text(string='Error')
    betask_id = fields.Many2one('myschool.betask', string='Related Betask', index=True, ondelete='set null')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('sync.log') or '/'
        return super().create(vals_list)

    @api.model
    def log_event(self, model_name, natural_key, action, direction,
                  sync_target=None, payload=None, success=True,
                  error_message=None, betask=None):
        """Convenience method to create a sync log entry."""
        import json
        vals = {
            'model_name': model_name,
            'record_natural_key': json.dumps(natural_key) if isinstance(natural_key, dict) else natural_key,
            'action': action,
            'direction': direction,
            'success': success,
            'error_message': error_message,
        }
        if sync_target:
            vals['sync_target_id'] = sync_target.id
        if payload:
            vals['payload'] = json.dumps(payload) if isinstance(payload, dict) else payload
        if betask:
            vals['betask_id'] = betask.id
        return self.sudo().create(vals)

    @api.model
    def cleanup_old_logs(self, days=90):
        """Archive logs older than N days. Called by cron."""
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)
        old_logs = self.search([
            ('create_date', '<', cutoff),
            ('success', '=', True),
        ])
        if old_logs:
            old_logs.unlink()
            _logger.info('Cleaned up %d old sync logs', len(old_logs))
