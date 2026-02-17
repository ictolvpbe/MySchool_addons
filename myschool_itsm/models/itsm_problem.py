from odoo import models, fields, api


class ItsmProblem(models.Model):
    _name = 'itsm.problem'
    _description = 'ITSM Problem'
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
    state = fields.Selection(
        [
            ('logged', 'Logged'),
            ('investigation', 'Investigation'),
            ('root_cause_identified', 'Root Cause Identified'),
            ('resolved', 'Resolved'),
            ('closed', 'Closed'),
        ],
        string='State',
        default='logged',
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
    root_cause = fields.Html(
        string='Root Cause',
    )
    workaround = fields.Html(
        string='Workaround',
    )
    permanent_fix = fields.Html(
        string='Permanent Fix',
    )
    is_known_error = fields.Boolean(
        string='Known Error',
        tracking=True,
    )
    ticket_ids = fields.One2many(
        'itsm.ticket',
        'problem_id',
        string='Related Tickets',
    )
    ticket_count = fields.Integer(
        string='Ticket Count',
        compute='_compute_ticket_count',
    )
    assigned_to_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        tracking=True,
    )
    related_ci_ids = fields.Many2many(
        'itsm.ci',
        string='Related CIs',
    )
    related_service_ids = fields.Many2many(
        'itsm.service',
        string='Related Services',
    )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'itsm.problem'
                ) or 'New'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for problem in self:
            problem.ticket_count = len(problem.ticket_ids)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_investigate(self):
        for problem in self:
            problem.state = 'investigation'

    def action_root_cause(self):
        for problem in self:
            problem.state = 'root_cause_identified'

    def action_resolve(self):
        for problem in self:
            problem.state = 'resolved'

    def action_close(self):
        for problem in self:
            problem.state = 'closed'

    def action_mark_known_error(self):
        for problem in self:
            problem.is_known_error = True

    def action_view_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Related Tickets',
            'res_model': 'itsm.ticket',
            'view_mode': 'list,form',
            'domain': [('problem_id', '=', self.id)],
        }
