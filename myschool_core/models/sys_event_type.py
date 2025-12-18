# -*- coding: utf-8 -*-
"""
System Event Type Model
Converted from SysEventType.java entity

This model stores the different types of system events that can occur.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SysEventType(models.Model):
    _name = 'myschool.sys.event.type'
    _description = 'System Event Type'
    _order = 'name'
    _inherit = ['mail.thread']

    # Core fields from Java entity
    name = fields.Char(
        string='Event Type Name',
        required=True,
        index=True,
        tracking=True,
        help='Name of the system event type (e.g., EVENT, ERROR-BLOCKING, ERROR-NONBLOCKING)'
    )
    
    code = fields.Char(
        string='Code',
        required=True,
        index=True,
        tracking=True,
        help='Unique code for the event type'
    )
    
    description = fields.Text(
        string='Description',
        help='Detailed description of this event type'
    )
    
    priority = fields.Selection(
        selection=[
            ('0', 'None'),
            ('1', 'High (Blocking)'),
            ('2', 'Normal'),
            ('3', 'Low'),
        ],
        string='Default Priority',
        default='2',
        help='Default priority for events of this type'
    )
    
    is_error_type = fields.Boolean(
        string='Is Error Type',
        compute='_compute_is_error_type',
        store=True,
        help='Indicates if this is an error type event'
    )
    
    is_blocking = fields.Boolean(
        string='Is Blocking',
        compute='_compute_is_blocking',
        store=True,
        help='Indicates if this error type is blocking'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='If unchecked, this event type will be hidden'
    )
    
    # Relation to events
    event_ids = fields.One2many(
        comodel_name='myschool.sys.event',
        inverse_name='syseventtype_id',
        string='Events',
        help='Events of this type'
    )
    
    # Statistics
    event_count = fields.Integer(
        string='Event Count',
        compute='_compute_event_count',
        store=True
    )
    
    open_event_count = fields.Integer(
        string='Open Events',
        compute='_compute_event_statistics'
    )
    
    error_event_count = fields.Integer(
        string='Error Events',
        compute='_compute_event_statistics'
    )
    
    @api.depends('name')
    def _compute_is_error_type(self):
        for record in self:
            record.is_error_type = 'ERROR' in (record.name or '').upper()
    
    @api.depends('name')
    def _compute_is_blocking(self):
        for record in self:
            record.is_blocking = 'BLOCKING' in (record.name or '').upper() and 'NON' not in (record.name or '').upper()
    
    @api.depends('event_ids')
    def _compute_event_count(self):
        for record in self:
            record.event_count = len(record.event_ids)
    
    def _compute_event_statistics(self):
        for record in self:
            events = record.event_ids
            record.open_event_count = len(events.filtered(lambda e: e.status in ['NEW', 'PROCESS']))
            record.error_event_count = len(events.filtered(lambda e: e.status == 'PRO_ERROR'))
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-generate code from name if not provided
            if not vals.get('code') and vals.get('name'):
                vals['code'] = vals['name'].replace(' ', '_').replace('-', '_').upper()
        return super().create(vals_list)
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The event type code must be unique!'),
        ('name_unique', 'unique(name)', 'The event type name must be unique!')
    ]

    def action_view_events(self):
        """Open events of this type"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Events: %s') % self.name,
            'res_model': 'myschool.sys.event',
            'view_mode': 'list,form',
            'domain': [('syseventtype_id', '=', self.id)],
            'context': {'default_syseventtype_id': self.id},
        }
