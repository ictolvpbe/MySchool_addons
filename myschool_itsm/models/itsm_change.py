from odoo import models, fields, api


class ItsmChange(models.Model):
    _name = 'itsm.change'
    _description = 'ITSM Change Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    title = fields.Char(
        string='Title',
        required=True,
        tracking=True,
    )
    description = fields.Html(
        string='Description',
    )
    change_type = fields.Selection(
        [
            ('standard', 'Standard'),
            ('normal', 'Normal'),
            ('emergency', 'Emergency'),
        ],
        string='Change Type',
        default='normal',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('assessment', 'Assessment'),
            ('approved', 'Approved'),
            ('scheduled', 'Scheduled'),
            ('implementing', 'Implementing'),
            ('review', 'Review'),
            ('closed', 'Closed'),
            ('rejected', 'Rejected'),
        ],
        string='State',
        default='draft',
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
    )
    risk_level = fields.Selection(
        [
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical'),
        ],
        string='Risk Level',
        default='medium',
    )
    impact_analysis = fields.Html(
        string='Impact Analysis',
    )
    rollback_plan = fields.Html(
        string='Rollback Plan',
    )
    implementation_plan = fields.Html(
        string='Implementation Plan',
    )
    scheduled_start = fields.Datetime(
        string='Scheduled Start',
    )
    scheduled_end = fields.Datetime(
        string='Scheduled End',
    )
    actual_start = fields.Datetime(
        string='Actual Start',
    )
    actual_end = fields.Datetime(
        string='Actual End',
    )
    requested_by_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
    )
    assigned_to_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        tracking=True,
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
    )
    approval_date = fields.Datetime(
        string='Approval Date',
    )
    affected_asset_ids = fields.Many2many(
        'myschool.asset',
        string='Affected Assets',
    )
    affected_ci_ids = fields.Many2many(
        'itsm.ci',
        string='Affected CIs',
    )
    affected_service_ids = fields.Many2many(
        'itsm.service',
        string='Affected Services',
    )
    ticket_ids = fields.Many2many(
        'itsm.ticket',
        string='Related Tickets',
    )
    review_notes = fields.Html(
        string='Review Notes',
    )
    success = fields.Boolean(
        string='Successful',
    )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'itsm.change'
                ) or 'New'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_assess(self):
        for change in self:
            change.state = 'assessment'

    def action_approve(self):
        for change in self:
            change.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })

    def action_reject(self):
        for change in self:
            change.state = 'rejected'

    def action_schedule(self):
        for change in self:
            change.state = 'scheduled'

    def action_implement(self):
        for change in self:
            change.write({
                'state': 'implementing',
                'actual_start': fields.Datetime.now(),
            })

    def action_review(self):
        for change in self:
            change.write({
                'state': 'review',
                'actual_end': fields.Datetime.now(),
            })

    def action_close(self):
        for change in self:
            change.state = 'closed'
