# -*- coding: utf-8 -*-
"""
Server extension (SRVMGR-7)
===========================
Koppelt het Server Manager-register (``myschool.server``) aan de
sync-targets. De afhankelijkheid loopt myschool_sync → myschool_servermanager,
dus de reverse-relatie hoort hier thuis (niet in servermanager).

Lichte koppeling (D1=A): een server toont z'n gekoppelde sync-targets via
een smart button; de sync zelf blijft op ``sync.target.url``/``api_key`` draaien.
"""

from odoo import models, fields, api, _


class MyschoolServer(models.Model):
    _inherit = 'myschool.server'

    sync_target_ids = fields.One2many(
        'sync.target', 'server_id', string='Sync Targets')
    sync_target_count = fields.Integer(
        compute='_compute_sync_target_count', string='Sync Targets')

    @api.depends('sync_target_ids')
    def _compute_sync_target_count(self):
        for server in self:
            server.sync_target_count = len(server.sync_target_ids)

    def action_open_sync_targets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Targets'),
            'res_model': 'sync.target',
            'view_mode': 'list,form',
            'domain': [('server_id', '=', self.id)],
            'context': {'default_server_id': self.id},
        }
