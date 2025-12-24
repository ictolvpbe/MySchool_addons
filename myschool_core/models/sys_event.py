# -*- coding: utf-8 -*-
"""
System Event Model
Converted from SysEvent.java entity

This model stores system events for logging, monitoring, and error tracking.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SysEvent(models.Model):
    _name = 'myschool.sys.event'
    _description = 'System Event'
    _order = 'create_date desc, priority'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Sequence field
    name = fields.Char(
        string='Event Reference',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
        help='Unique reference for this event'
    )
    
    # Core fields matching Java entity
    syseventtype_id = fields.Many2one(
        comodel_name='myschool.sys.event.type',
        string='Event Type',
        required=True,
        index=True,
        ondelete='restrict',
        #Tracking=True,
        help='Type of system event (EVENT, ERROR-BLOCKING, ERROR-NONBLOCKING)'
    )
    
    source = fields.Selection(
        selection=[
            ('BE', 'Backend'),
            ('FE', 'Frontend'),
            ('ADSYNC', 'AD Sync'),
            ('SAPSYNC', 'SAP Sync'),
            ('API', 'API'),
            ('CRON', 'Scheduled Task'),
            ('USER', 'User Action'),
            ('IMPORT', 'Data Import'),
            ('EXPORT', 'Data Export'),
            ('OTHER', 'Other'),
        ],
        string='Source',
        required=True,
        default='BE',
        index=True,
        #Tracking=True,
        help='Source system that generated this event'
    )
    
    eventcode = fields.Char(
        string='Event Code',
        size=100,
        index=True,
        #Tracking=True,
        help='Specific code identifying the event (pCode from Java)'
    )
    
    priority = fields.Selection(
        selection=[
            ('0', 'None'),
            ('1', 'High'),
            ('2', 'Normal'),
            ('3', 'Low'),
        ],
        string='Priority',
        default='2',
        required=True,
        index=True,
        #Tracking=True,
        help='Priority level: 1-High (blocking errors), 2-Normal, 3-Low'
    )
    
    data = fields.Text(
        string='Event Data',
        #Tracking=True,
        help='Detailed data associated with this event (pData from Java)'
    )
    
    status = fields.Selection(
        selection=[
            ('NEW', 'New'),
            ('PROCESS', 'Processing'),
            ('PRO_ERROR', 'Processing Error'),
            ('CLOSED', 'Closed'),
        ],
        string='Status',
        required=True,
        default='NEW',
        index=True,
        #Tracking=True,
        help='Current status of the event'
    )
    
    eventclosed = fields.Datetime(
        string='Event Closed Date',
        readonly=True,
        #Tracking=True,
        help='Date and time when the event was closed'
    )
    
    # Additional #Tracking fields
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this event will be archived'
    )
    
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        help='Company associated with this event'
    )
    
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Responsible User',
        default=lambda self: self.env.user,
        #Tracking=True,
        help='User responsible for this event'
    )
    
    # Related fields for easy access
    event_type_name = fields.Char(
        related='syseventtype_id.name',
        string='Type Name',
        store=True
    )
    
    is_error = fields.Boolean(
        related='syseventtype_id.is_error_type',
        string='Is Error',
        store=True
    )
    
    is_blocking = fields.Boolean(
        related='syseventtype_id.is_blocking',
        string='Is Blocking',
        store=True
    )
    
    # Computed fields
    priority_label = fields.Char(
        string='Priority Label',
        compute='_compute_priority_label',
        store=True
    )
    
    is_closed = fields.Boolean(
        string='Is Closed',
        compute='_compute_is_closed',
        store=True
    )
    
    duration_hours = fields.Float(
        string='Duration (Hours)',
        compute='_compute_duration',
        store=True,
        help='Hours from creation to closure'
    )
    
    duration_days = fields.Integer(
        string='Duration (Days)',
        compute='_compute_duration',
        store=True,
        help='Days from creation to closure'
    )
    
    color = fields.Integer(
        string='Color',
        compute='_compute_color'
    )
    
    @api.depends('priority')
    def _compute_priority_label(self):
        priority_map = {
            '0': _('None'),
            '1': _('High'),
            '2': _('Normal'),
            '3': _('Low'),
        }
        for record in self:
            record.priority_label = priority_map.get(record.priority, _('Unknown'))
    
    @api.depends('status')
    def _compute_is_closed(self):
        for record in self:
            record.is_closed = record.status == 'CLOSED'
    
    @api.depends('create_date', 'eventclosed')
    def _compute_duration(self):
        for record in self:
            if record.eventclosed and record.create_date:
                delta = record.eventclosed - record.create_date
                record.duration_hours = delta.total_seconds() / 3600
                record.duration_days = delta.days
            else:
                record.duration_hours = 0
                record.duration_days = 0
    
    @api.depends('status', 'priority')
    def _compute_color(self):
        """Compute color for kanban view"""
        for record in self:
            if record.status == 'PRO_ERROR':
                record.color = 1  # Red
            elif record.status == 'CLOSED':
                record.color = 10  # Green
            elif record.status == 'PROCESS':
                record.color = 4  # Blue
            elif record.priority == '1':
                record.color = 2  # Orange (high priority new)
            else:
                record.color = 0  # Default
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('myschool.sys.event') or _('New')
        return super().create(vals_list)
    
    def write(self, vals):
        # Automatically set eventclosed when status changes to CLOSED
        if vals.get('status') == 'CLOSED' and 'eventclosed' not in vals:
            vals['eventclosed'] = fields.Datetime.now()
        
        # Clear eventclosed if status changes away from CLOSED
        if vals.get('status') and vals.get('status') != 'CLOSED':
            if 'eventclosed' not in vals:
                vals['eventclosed'] = False
        
        return super().write(vals)
    
    # Action methods (equivalent to Java service operations)
    def action_set_processing(self):
        """Set event status to Processing"""
        for record in self:
            record.write({'status': 'PROCESS'})
            _logger.info(f'SysEvent {record.name} set to PROCESSING')
    
    def action_set_error(self):
        """Set event status to Processing Error"""
        for record in self:
            record.write({'status': 'PRO_ERROR'})
            _logger.warning(f'SysEvent {record.name} set to PRO_ERROR')
    
    def action_set_closed(self):
        """Close the event"""
        for record in self:
            record.write({
                'status': 'CLOSED',
                'eventclosed': fields.Datetime.now()
            })
            _logger.info(f'SysEvent {record.name} CLOSED')
    
    def action_reopen(self):
        """Reopen a closed event"""
        for record in self:
            record.write({
                'status': 'NEW',
                'eventclosed': False
            })
            _logger.info(f'SysEvent {record.name} reopened')
    
    @api.constrains('priority')
    def _check_priority(self):
        for record in self:
            if record.priority not in ['0', '1', '2', '3']:
                raise ValidationError(_('Priority must be between 0 and 3'))
    
    def name_get(self):
        """Custom display name"""
        result = []
        for record in self:
            name = f"{record.name}"
            if record.eventcode:
                name += f" [{record.eventcode}]"
            result.append((record.id, name))
        return result
