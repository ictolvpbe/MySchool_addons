# -*- coding: utf-8 -*-
"""
Backend Task Model
Converted from BeTask.java entity

BeTask represents a background task to be executed.
Tasks are created by various processes (sync, user actions, etc.)
and processed by the BeTaskProcessor.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class BeTask(models.Model):
    _name = 'myschool.betask'
    _description = 'Backend Task'
    _order = 'create_date desc, id desc'
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Task Name',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
        help='Unique reference for this task'
    )
    
    # Core fields from Java entity
    betasktype_id = fields.Many2one(
        comodel_name='myschool.betask.type',
        string='Task Type',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
        help='Type of backend task (defines target, object, and action)'
    )
    
    status = fields.Selection(
        selection=[
            ('new', 'New'),
            ('processing', 'Processing'),
            ('completed_ok', 'Completed'),
            ('error', 'Error'),
        ],
        string='Status',
        required=True,
        default='new',
        index=True,
        tracking=True,
        help='Current status of the task'
    )
    
    automatic_sync = fields.Boolean(
        string='Automatic Sync',
        default=True,
        required=True,
        help='If checked, this task will be processed automatically by cron jobs'
    )
    
    data = fields.Text(
        string='Data',
        help='Primary data for task processing (usually JSON)'
    )
    
    data2 = fields.Text(
        string='Data 2',
        help='Secondary/additional data for task processing'
    )
    
    lastrun = fields.Datetime(
        string='Last Run',
        readonly=True,
        tracking=True,
        help='Date and time when the task was last processed'
    )
    
    error_description = fields.Text(
        string='Error Description',
        readonly=True,
        help='Description of error if task processing failed'
    )
    
    # Additional tracking fields
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this task will be archived'
    )
    
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Created By',
        default=lambda self: self.env.user,
        readonly=True
    )
    
    processed_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Processed By',
        readonly=True
    )
    
    processing_start = fields.Datetime(
        string='Processing Started',
        readonly=True
    )
    
    processing_end = fields.Datetime(
        string='Processing Ended',
        readonly=True
    )
    
    retry_count = fields.Integer(
        string='Retry Count',
        default=0,
        readonly=True,
        help='Number of times this task has been retried'
    )
    
    max_retries = fields.Integer(
        string='Max Retries',
        default=3,
        help='Maximum number of retry attempts'
    )
    
    # Related fields for easy access
    task_type_name = fields.Char(
        related='betasktype_id.name',
        string='Type Name',
        store=True
    )
    
    target = fields.Selection(
        related='betasktype_id.target',
        string='Target',
        store=True,
        readonly=True
    )
    
    object_type = fields.Selection(
        related='betasktype_id.object',
        string='Object',
        store=True,
        readonly=True
    )
    
    action = fields.Selection(
        related='betasktype_id.action',
        string='Action',
        store=True,
        readonly=True
    )
    
    # Computed fields
    is_processable = fields.Boolean(
        string='Can Process',
        compute='_compute_is_processable'
    )
    
    processing_duration = fields.Float(
        string='Processing Duration (sec)',
        compute='_compute_processing_duration',
        store=True
    )
    
    color = fields.Integer(
        string='Color',
        compute='_compute_color'
    )
    
    @api.depends('status', 'automatic_sync', 'retry_count', 'max_retries')
    def _compute_is_processable(self):
        for record in self:
            record.is_processable = (
                record.status in ['new', 'error'] and 
                record.automatic_sync and
                record.retry_count < record.max_retries
            )
    
    @api.depends('processing_start', 'processing_end')
    def _compute_processing_duration(self):
        for record in self:
            if record.processing_start and record.processing_end:
                delta = record.processing_end - record.processing_start
                record.processing_duration = delta.total_seconds()
            else:
                record.processing_duration = 0
    
    @api.depends('status')
    def _compute_color(self):
        """Compute color for kanban view"""
        color_map = {
            'new': 4,        # Blue
            'processing': 2,  # Orange
            'completed_ok': 10,  # Green
            'error': 1,      # Red
        }
        for record in self:
            record.color = color_map.get(record.status, 0)
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('status', _('new')) == _('new'):
                vals['status'] = self.env['ir.sequence'].next_by_code('myschool.betask') or _('new')
        return super().create(vals_list)
    
    # ==========================================================================
    # Action Methods (Status Transitions)
    # ==========================================================================
    
    def action_set_processing(self):
        """Set task status to Processing"""
        for record in self:
            record.write({
                'status': 'processing',
                'processing_start': fields.Datetime.now(),
                'processed_by_id': self.env.user.id,
            })
            _logger.info(f'BeTask {record.name} set to PROCESSING')
    
    def action_set_completed(self, result_data=None):
        """Set task status to Completed"""
        now = fields.Datetime.now()
        for record in self:
            vals = {
                'status': 'completed_ok',
                'processing_end': now,
                'lastrun': now,
                'error_description': False,
            }
            if result_data:
                vals['data2'] = str(result_data)
            record.write(vals)
            _logger.info(f'BeTask {record.name} COMPLETED')
    
    def action_set_error(self, error_msg=None):
        """Set task status to Error"""
        now = fields.Datetime.now()
        for record in self:
            record.write({
                'status': 'error',
                'processing_end': now,
                'lastrun': now,
                'error_description': error_msg or f'Check SysEvents @ timestamp: {now}',
                'retry_count': record.retry_count + 1,
            })
            _logger.warning(f'BeTask {record.name} ERROR: {error_msg}')
    
    def action_reset_to_new(self):
        """Reset task to New status (for retry)"""
        for record in self:
            if record.retry_count >= record.max_retries:
                raise ValidationError(
                    _('Task %s has exceeded maximum retry attempts (%d)') 
                    % (record.name, record.max_retries)
                )
            record.write({
                'status': 'new',
                'processing_start': False,
                'processing_end': False,
                'error_description': False,
            })
            _logger.info(f'BeTask {record.name} reset to NEW')
    
    def action_force_reset(self):
        """Force reset task (reset retry count as well)"""
        for record in self:
            record.write({
                'status': 'new',
                'processing_start': False,
                'processing_end': False,
                'error_description': False,
                'retry_count': 0,
            })
            _logger.info(f'BeTask {record.name} FORCE RESET')
    
    def action_process_single(self):
        """Process this single task immediately"""
        self.ensure_one()
        processor = self.env['myschool.betask.processor']
        result = processor.process_single_task(self)
        
        notification_type = 'success' if result else 'danger'
        message = _('Task processed successfully') if result else _('Task processing failed')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Task Processing'),
                'message': message,
                'type': notification_type,
                'sticky': False,
            }
        }
    
    def action_view_sys_events(self):
        """View related system events"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Related Events'),
            'res_model': 'myschool.sys.event',
            'view_mode': 'list,form',
            'domain': [('data', 'ilike', self.name)],
            'context': {'search_default_today': 1},
        }
    
    def name_get(self):
        """Custom display name"""
        result = []
        for record in self:
            name = f"{record.name}"
            if record.betasktype_id:
                name += f" [{record.betasktype_id.name}]"
            result.append((record.id, name))
        return result
