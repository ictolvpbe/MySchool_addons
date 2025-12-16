# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SysEventType(models.Model):
    _name = 'myschool.sys.event.type'
    _description = 'System Event Type'
    _order = 'name'

    name = fields.Char(
        string='Event Type Name',
        required=True,
        index=True,
        help='Name of the system event type'
    )
    
    code = fields.Char(
        string='Code',
        required=True,
        index=True,
        help='Unique code for the event type'
    )
    
    description = fields.Text(
        string='Description',
        help='Detailed description of this event type'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this event type will be hidden'
    )
    
    event_ids = fields.One2many(
        comodel_name='myschool.sys.event',
        inverse_name='syseventtype_id',
        string='Events',
        help='Events of this type'
    )
    
    event_count = fields.Integer(
        string='Event Count',
        compute='_compute_event_count',
        store=True
    )
    
    @api.depends('event_ids')
    def _compute_event_count(self):
        for record in self:
            record.event_count = len(record.event_ids)
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The event type code must be unique!')
    ]

