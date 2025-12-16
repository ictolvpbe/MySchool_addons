# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SysEvent(models.Model):
    _name = 'myschool.sys.event'
    _description = 'System Event'
    _order = 'create_date desc, priority'
    # _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Event Reference',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
        help='Unique reference for this event'
    )
    
    syseventtype_id = fields.Many2one(
        comodel_name='myschool.sys.event.type',
        string='Event Type',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
        help='Type of system event'
    )
    
    source = fields.Selection(
        selection=[
            ('BE', 'Backend'),
            ('ADSYNC', 'AD Sync'),
            ('API', 'API'),
            ('CRON', 'Scheduled Task'),
            ('USER', 'User Action'),
            ('OTHER', 'Other'),
        ],
        string='Source',
        required=True,
        default='BE',
        tracking=True,
        help='Source system that generated this event'
    )
    
    eventcode = fields.Char(
        string='Event Code',
        size=50,
        index=True,
        tracking=True,
        help='Specific code identifying the event'
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
        tracking=True,
        help='Priority level: 0-None, 1-High, 2-Normal, 3-Low'
    )
    
    data = fields.Text(
        string='Event Data',
        help='Detailed data associated with this event'
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
        tracking=True,
        help='Current status of the event'
    )
    
    eventclosed = fields.Datetime(
        string='Event Closed Date',
        readonly=True,
        tracking=True,
        help='Date and time when the event was closed'
    )
    
    # Additional helpful fields
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
        tracking=True,
        help='User responsible for this event'
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
    
    duration_days = fields.Integer(
        string='Duration (Days)',
        compute='_compute_duration',
        help='Number of days from creation to closure'
    )
    
    @api.depends('priority')
    def _compute_priority_label(self):
        priority_map = {
            '0': 'None',
            '1': 'High',
            '2': 'Normal',
            '3': 'Low',
        }
        for record in self:
            record.priority_label = priority_map.get(record.priority, 'Unknown')
    
    @api.depends('status')
    def _compute_is_closed(self):
        for record in self:
            record.is_closed = record.status == 'CLOSED'
    
    @api.depends('create_date', 'eventclosed')
    def _compute_duration(self):
        for record in self:
            if record.eventclosed and record.create_date:
                delta = record.eventclosed - record.create_date
                record.duration_days = delta.days
            else:
                record.duration_days = 0
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('myschool.sys.event') or _('New')
        return super(SysEvent, self).create(vals_list)
    
    def write(self, vals):
        # Automatically set eventclosed when status changes to CLOSED
        if vals.get('status') == 'CLOSED' and 'eventclosed' not in vals:
            vals['eventclosed'] = fields.Datetime.now()
        
        # Clear eventclosed if status changes away from CLOSED
        if vals.get('status') and vals.get('status') != 'CLOSED':
            if 'eventclosed' not in vals:
                vals['eventclosed'] = False
        
        return super(SysEvent, self).write(vals)
    
    def action_set_processing(self):
        """Set event status to Processing"""
        self.ensure_one()
        self.write({'status': 'PROCESS'})
    
    def action_set_error(self):
        """Set event status to Processing Error"""
        self.ensure_one()
        self.write({'status': 'PRO_ERROR'})
    
    def action_set_closed(self):
        """Close the event"""
        self.ensure_one()
        self.write({
            'status': 'CLOSED',
            'eventclosed': fields.Datetime.now()
        })
    
    def action_reopen(self):
        """Reopen a closed event"""
        self.ensure_one()
        self.write({
            'status': 'NEW',
            'eventclosed': False
        })
    
    @api.constrains('priority')
    def _check_priority(self):
        for record in self:
            if record.priority not in ['0', '1', '2', '3']:
                raise ValidationError(_('Priority must be between 0 and 3'))


