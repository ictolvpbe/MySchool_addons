# -*- coding: utf-8 -*-
"""
Backend Task Type Model
Converted from BeTaskType.java entity

BeTaskType defines the type of backend task based on:
- TARGET: Where to execute (DB, AD/LDAP, CLOUD, etc.)
- OBJECT: What entity to affect (ORG, PERSON, ROLE, etc.)
- ACTION: What operation to perform (ADD, UPD, DEL, etc.)
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class BeTaskType(models.Model):
    _name = 'myschool.betask.type'
    _description = 'Backend Task Type'
    _order = 'target, object, action'
    _rec_name = 'name'

    name = fields.Char(
        string='Name',
        required=True,
        index=True,
        help='Unique name for the task type (auto-generated from TARGET_OBJECT_ACTION)'
    )
    
    target = fields.Selection(
        selection=[
            ('DB', 'Database'),
            ('ODOO', 'Odoo'),
            ('LDAP', 'LDAP/Active Directory'),
            ('AD', 'Active Directory'),
            ('CLOUD', 'Cloud Service'),
            ('API', 'External API'),
            ('EMAIL', 'Email Service'),
            ('ALL', 'All Systems'),
            ('MANUAL', 'Manual Action'),
        ],
        string='Target',
        required=True,
        index=True,
        help='Target system where the action will be executed (DB, AD, CLOUD, etc.)'
    )
    
    object = fields.Selection(
        selection=[
            ('ORG', 'Organization'),
            ('PERSON', 'Person'),
            ('GROUPMEMBER','Groupmember'),
            ('STUDENT', 'Student'),
            ('EMPLOYEE', 'Employee'),
            ('ROLE', 'Role'),
            ('PERIOD', 'Period'),
            ('PROPRELATION', 'Prop Relation'),
            ('COM_EMAIL', 'Email Address'),
            ('COM_ADDRESS', 'Physical Address'),
            ('COM_PHONE', 'Phone Number'),
            ('USER', 'User Account'),
            ('GROUP', 'Group'),
            ('CONFIG', 'Configuration'),
        ],
        string='Object',
        required=True,
        index=True,
        help='Object type to be affected (ORG, PERSON, ROLE, etc.)'
    )
    
    action = fields.Selection(
        selection=[
            ('ADD', 'Add/Create'),
            ('UPD', 'Update'),
            #('UPDATE', 'Update _'),  # Alias for compatibility
            ('DEL', 'Delete'),
            ('REMOVE', 'Remove'),
            ('DEACT', 'Deactivate'),
            ('ARC', 'Archive'),
            ('SYNC', 'Synchronize'),
            ('MANUAL', 'Manual Action'),
        ],
        string='Action',
        required=True,
        index=True,
        help='Action to perform (ADD, UPD, DEL, DEACT, ARC)'
    )
    
    description = fields.Text(
        string='Description',
        help='Detailed description of what this task type does'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this task type will be hidden'
    )
    
    # Processing configuration
    processor_method = fields.Char(
        string='Processor Method',
        help='Name of the method to call in the processor service (e.g., process_db_org_add)'
    )
    
    requires_confirmation = fields.Boolean(
        string='Requires Confirmation',
        default=False,
        help='If checked, tasks of this type require manual confirmation before processing'
    )
    
    auto_process = fields.Boolean(
        string='Auto Process',
        default=True,
        help='If checked, tasks of this type will be processed automatically by cron'
    )
    
    priority = fields.Integer(
        string='Processing Priority',
        default=10,
        help='Lower number = higher priority. Tasks are processed in priority order.'
    )
    
    # Relations
    task_ids = fields.One2many(
        comodel_name='myschool.betask',
        inverse_name='betasktype_id',
        string='Tasks'
    )
    
    # Statistics
    task_count = fields.Integer(
        string='Total Tasks',
        compute='_compute_task_statistics',
        store=True
    )
    
    pending_task_count = fields.Integer(
        string='Pending Tasks',
        compute='_compute_task_statistics'
    )
    
    error_task_count = fields.Integer(
        string='Error Tasks',
        compute='_compute_task_statistics'
    )
    
    @api.depends('task_ids', 'task_ids.status')
    def _compute_task_statistics(self):
        for record in self:
            tasks = record.task_ids
            record.task_count = len(tasks)
            record.pending_task_count = len(tasks.filtered(lambda t: t.status == 'new'))
            record.error_task_count = len(tasks.filtered(lambda t: t.status == 'error'))
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-generate name if not provided
            if not vals.get('name'):
                target = vals.get('target', '')
                obj = vals.get('object', '')
                action = vals.get('action', '')
                vals['name'] = f"{target}_{obj}_{action}"
            
            # Auto-generate processor method name
            if not vals.get('processor_method'):
                target = vals.get('target', '').lower()
                obj = vals.get('object', '').lower()
                action = vals.get('action', '').lower()
                vals['processor_method'] = f"process_{target}_{obj}_{action}"
        
        return super().create(vals_list)
    
    def write(self, vals):
        # Regenerate name if components change
        if any(k in vals for k in ['target', 'object', 'action']):
            for record in self:
                target = vals.get('target', record.target)
                obj = vals.get('object', record.object)
                action = vals.get('action', record.action)
                vals['name'] = f"{target}_{obj}_{action}"
        return super().write(vals)
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Task type name must be unique!'),
        ('target_object_action_unique', 
         'UNIQUE(target, object, action)', 
         'The combination of Target, Object, and Action must be unique!')
    ]
    
    def action_view_tasks(self):
        """Open tasks of this type"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tasks: %s') % self.name,
            'res_model': 'myschool.betask',
            'view_mode': 'list,form',
            'domain': [('betasktype_id', '=', self.id)],
            'context': {'default_betasktype_id': self.id},
        }
    
    def action_view_pending_tasks(self):
        """Open pending tasks of this type"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pending Tasks: %s') % self.name,
            'res_model': 'myschool.betask',
            'view_mode': 'list,form',
            'domain': [('betasktype_id', '=', self.id), ('status', '=', 'new')],
            'context': {'default_betasktype_id': self.id},
        }
    
    def action_process_tasks(self):
        """Process all pending tasks of this type"""
        self.ensure_one()
        processor = self.env['myschool.betask.processor']
        result = processor.process_tasks_by_type(self)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Task Processing'),
                'message': _('Processed tasks for type: %s') % self.name,
                'type': 'success' if result else 'warning',
                'sticky': False,
            }
        }
