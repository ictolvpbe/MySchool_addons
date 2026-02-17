from odoo import models, fields, api
from odoo.tools import email_split
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class ItsmTicket(models.Model):
    _name = 'itsm.ticket'
    _description = 'ITSM Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_created desc, id desc'
    _mail_post_access = 'read'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    subject = fields.Char(
        string='Subject',
        required=True,
        tracking=True,
    )
    description = fields.Html(
        string='Description',
    )
    ticket_type = fields.Selection(
        [
            ('incident', 'Incident'),
            ('service_request', 'Service Request'),
        ],
        string='Type',
        required=True,
        default='incident',
        tracking=True,
    )
    state = fields.Selection(
        [
            ('new', 'New'),
            ('assigned', 'Assigned'),
            ('in_progress', 'In Progress'),
            ('pending', 'Pending'),
            ('resolved', 'Resolved'),
            ('closed', 'Closed'),
            ('cancelled', 'Cancelled'),
        ],
        string='State',
        default='new',
        required=True,
        tracking=True,
    )
    priority = fields.Selection(
        [
            ('p1', 'P1 - Critical'),
            ('p2', 'P2 - High'),
            ('p3', 'P3 - Medium'),
            ('p4', 'P4 - Low'),
        ],
        string='Priority',
        default='p3',
        required=True,
        tracking=True,
    )
    impact = fields.Selection(
        [
            ('high', 'High'),
            ('medium', 'Medium'),
            ('low', 'Low'),
        ],
        string='Impact',
        default='medium',
    )
    urgency = fields.Selection(
        [
            ('high', 'High'),
            ('medium', 'Medium'),
            ('low', 'Low'),
        ],
        string='Urgency',
        default='medium',
    )
    category_id = fields.Many2one(
        'itsm.service.category',
        string='Category',
    )
    service_id = fields.Many2one(
        'itsm.service',
        string='Service',
    )
    assigned_to_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        tracking=True,
    )
    reported_by_id = fields.Many2one(
        'myschool.person',
        string='Reported By',
    )
    reporter_email = fields.Char(
        string='Reporter Email',
    )
    asset_ids = fields.Many2many(
        'asset.asset',
        string='Related Assets',
    )
    problem_id = fields.Many2one(
        'itsm.problem',
        string='Related Problem',
    )
    change_id = fields.Many2one(
        'itsm.change',
        string='Related Change',
    )
    sla_id = fields.Many2one(
        'itsm.sla',
        string='SLA',
        compute='_compute_sla',
        store=True,
    )
    sla_response_deadline = fields.Datetime(
        string='Response Deadline',
        compute='_compute_sla_deadlines',
        store=True,
    )
    sla_resolution_deadline = fields.Datetime(
        string='Resolution Deadline',
        compute='_compute_sla_deadlines',
        store=True,
    )
    sla_response_met = fields.Boolean(
        string='Response SLA Met',
        compute='_compute_sla_status',
        store=True,
    )
    sla_resolution_met = fields.Boolean(
        string='Resolution SLA Met',
        compute='_compute_sla_status',
        store=True,
    )
    is_major_incident = fields.Boolean(
        string='Major Incident',
    )
    resolution_notes = fields.Html(
        string='Resolution Notes',
    )
    date_created = fields.Datetime(
        string='Date Created',
        default=fields.Datetime.now,
        readonly=True,
    )
    date_assigned = fields.Datetime(
        string='Date Assigned',
        readonly=True,
    )
    date_resolved = fields.Datetime(
        string='Date Resolved',
        readonly=True,
    )
    date_closed = fields.Datetime(
        string='Date Closed',
        readonly=True,
    )
    duration_to_response = fields.Float(
        string='Time to Response (Hours)',
        compute='_compute_duration_to_response',
        store=True,
    )
    duration_to_resolution = fields.Float(
        string='Time to Resolution (Hours)',
        compute='_compute_duration_to_resolution',
        store=True,
    )
    approval_required = fields.Boolean(
        string='Approval Required',
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
    )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                ticket_type = vals.get('ticket_type', 'incident')
                if ticket_type == 'service_request':
                    vals['name'] = self.env['ir.sequence'].next_by_code(
                        'itsm.ticket.request'
                    ) or 'New'
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code(
                        'itsm.ticket.incident'
                    ) or 'New'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('service_id', 'ticket_type', 'priority')
    def _compute_sla(self):
        for ticket in self:
            sla = False
            if ticket.service_id and ticket.ticket_type and ticket.priority:
                sla = self.env['itsm.sla'].search([
                    ('service_id', '=', ticket.service_id.id),
                    ('ticket_type', '=', ticket.ticket_type),
                    ('priority', '=', ticket.priority),
                    ('active', '=', True),
                ], limit=1)
            ticket.sla_id = sla

    @api.depends('sla_id', 'date_created',
                 'sla_id.response_time_hours', 'sla_id.resolution_time_hours')
    def _compute_sla_deadlines(self):
        for ticket in self:
            if ticket.sla_id and ticket.date_created:
                ticket.sla_response_deadline = ticket.date_created + timedelta(
                    hours=ticket.sla_id.response_time_hours
                )
                ticket.sla_resolution_deadline = ticket.date_created + timedelta(
                    hours=ticket.sla_id.resolution_time_hours
                )
            else:
                ticket.sla_response_deadline = False
                ticket.sla_resolution_deadline = False

    @api.depends('sla_response_deadline', 'sla_resolution_deadline',
                 'date_assigned', 'date_resolved')
    def _compute_sla_status(self):
        for ticket in self:
            if ticket.sla_response_deadline and ticket.date_assigned:
                ticket.sla_response_met = ticket.date_assigned <= ticket.sla_response_deadline
            else:
                ticket.sla_response_met = True
            if ticket.sla_resolution_deadline and ticket.date_resolved:
                ticket.sla_resolution_met = ticket.date_resolved <= ticket.sla_resolution_deadline
            else:
                ticket.sla_resolution_met = True

    @api.depends('date_created', 'date_assigned')
    def _compute_duration_to_response(self):
        for ticket in self:
            if ticket.date_created and ticket.date_assigned:
                delta = ticket.date_assigned - ticket.date_created
                ticket.duration_to_response = delta.total_seconds() / 3600.0
            else:
                ticket.duration_to_response = 0.0

    @api.depends('date_created', 'date_resolved')
    def _compute_duration_to_resolution(self):
        for ticket in self:
            if ticket.date_created and ticket.date_resolved:
                delta = ticket.date_resolved - ticket.date_created
                ticket.duration_to_resolution = delta.total_seconds() / 3600.0
            else:
                ticket.duration_to_resolution = 0.0

    # ------------------------------------------------------------------
    # Onchange: Priority matrix
    # ------------------------------------------------------------------

    @api.onchange('impact', 'urgency')
    def _compute_priority(self):
        """Auto-compute priority from impact + urgency matrix."""
        matrix = {
            ('high', 'high'): 'p1',
            ('high', 'medium'): 'p2',
            ('medium', 'high'): 'p2',
            ('high', 'low'): 'p3',
            ('medium', 'medium'): 'p3',
            ('low', 'high'): 'p3',
            ('medium', 'low'): 'p4',
            ('low', 'medium'): 'p4',
            ('low', 'low'): 'p4',
        }
        for ticket in self:
            if ticket.impact and ticket.urgency:
                ticket.priority = matrix.get(
                    (ticket.impact, ticket.urgency), 'p3'
                )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_assign(self):
        for ticket in self:
            ticket.write({
                'assigned_to_id': self.env.user.id,
                'state': 'assigned',
                'date_assigned': fields.Datetime.now(),
            })

    def action_start(self):
        for ticket in self:
            ticket.state = 'in_progress'

    def action_pending(self):
        for ticket in self:
            ticket.state = 'pending'

    def action_resolve(self):
        for ticket in self:
            ticket.write({
                'state': 'resolved',
                'date_resolved': fields.Datetime.now(),
            })

    def action_close(self):
        for ticket in self:
            ticket.write({
                'state': 'closed',
                'date_closed': fields.Datetime.now(),
            })

    def action_cancel(self):
        for ticket in self:
            ticket.state = 'cancelled'

    def action_reopen(self):
        for ticket in self:
            ticket.write({
                'state': 'in_progress',
                'date_resolved': False,
                'date_closed': False,
            })

    def action_approve(self):
        for ticket in self:
            ticket.write({
                'approved_by_id': self.env.user.id,
                'approval_required': False,
            })

    def action_send_reply(self):
        """Open the mail composer to reply to the reporter."""
        self.ensure_one()
        template = self.env.ref(
            'myschool_itsm.mail_template_ticket_reply',
            raise_if_not_found=False,
        )
        ctx = dict(
            default_model='itsm.ticket',
            default_res_ids=self.ids,
            default_composition_mode='comment',
            default_email_layout_xmlid=(
                'mail.mail_notification_layout_with_responsible_signature'
            ),
            force_email=True,
        )
        if template:
            ctx['default_template_id'] = template.id
        return {
            'name': 'Reply to Customer',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'target': 'new',
            'context': ctx,
        }

    # ------------------------------------------------------------------
    # Mail integration
    # ------------------------------------------------------------------

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """Create a new ticket from an incoming email."""
        ICP = self.env['ir.config_parameter'].sudo()
        defaults = dict(custom_values or {})

        # Subject → ticket subject
        defaults.setdefault(
            'subject', msg_dict.get('subject', 'No Subject'),
        )
        # Email body → description
        defaults.setdefault('description', msg_dict.get('body', ''))

        # Default ticket type from configuration
        defaults.setdefault(
            'ticket_type',
            ICP.get_param('myschool_itsm.default_ticket_type', 'incident'),
        )

        # Reporter email
        email_from = msg_dict.get('email_from', '')
        if email_from:
            addresses = email_split(email_from)
            email_addr = addresses[0] if addresses else email_from
            defaults.setdefault('reporter_email', email_addr)
            # Try to find a myschool.person by email
            Person = self.env['myschool.person']
            person = Person.search([
                '|',
                ('email_cloud', '=ilike', email_addr),
                ('email_private', '=ilike', email_addr),
            ], limit=1)
            if person:
                defaults.setdefault('reported_by_id', person.id)

        ticket = super().message_new(msg_dict, custom_values=defaults)

        # Add the sender as a follower so replies reach them
        if email_from:
            partner = self.env['res.partner'].search(
                [('email', '=ilike', email_split(email_from)[0])], limit=1,
            ) if email_split(email_from) else False
            if partner:
                ticket.message_subscribe(partner_ids=partner.ids)

        # Send auto-acknowledgment if configured
        auto_reply = ICP.get_param(
            'myschool_itsm.auto_reply', 'True'
        ) == 'True'
        if auto_reply:
            template = self.env.ref(
                'myschool_itsm.mail_template_ticket_acknowledgment',
                raise_if_not_found=False,
            )
            if template:
                template.send_mail(ticket.id, force_send=True)

        _logger.info(
            'ITSM ticket %s created from email (from: %s)',
            ticket.name, email_from,
        )
        return ticket

    def message_update(self, msg_dict, update_vals=None):
        """Handle a follow-up email on an existing ticket."""
        # Reopen the ticket if it was resolved or closed
        if self.state in ('resolved', 'closed'):
            self.write({'state': 'in_progress'})
            _logger.info(
                'ITSM ticket %s reopened from follow-up email', self.name,
            )
        return super().message_update(msg_dict, update_vals=update_vals)
