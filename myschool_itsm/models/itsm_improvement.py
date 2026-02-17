from odoo import models, fields, api


class ItsmImprovement(models.Model):
    _name = 'itsm.improvement'
    _description = 'ITSM Continual Improvement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default='New')
    title = fields.Char(string='Title', required=True, tracking=True)
    description = fields.Html(string='Description')
    state = fields.Selection(
        [
            ('idea', 'Idea'),
            ('assessment', 'Assessment'),
            ('approved', 'Approved'),
            ('implementing', 'Implementing'),
            ('done', 'Done'),
            ('rejected', 'Rejected'),
        ],
        string='State',
        default='idea',
        tracking=True,
    )
    priority = fields.Selection(
        [
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
        ],
        string='Priority',
        default='medium',
    )
    source = fields.Selection(
        [
            ('incident', 'Incident Analysis'),
            ('problem', 'Problem Analysis'),
            ('feedback', 'User Feedback'),
            ('audit', 'Audit'),
            ('other', 'Other'),
        ],
        string='Source',
    )
    expected_benefit = fields.Html(string='Expected Benefit')
    measurable_target = fields.Text(string='Measurable Target')
    actual_result = fields.Html(string='Actual Result')
    source_ticket_id = fields.Many2one('itsm.ticket', string='Source Ticket')
    source_problem_id = fields.Many2one('itsm.problem', string='Source Problem')
    assigned_to_id = fields.Many2one('res.users', string='Assigned To', tracking=True)
    target_date = fields.Date(string='Target Date')
    completion_date = fields.Date(string='Completion Date')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'itsm.improvement'
                ) or 'New'
        return super().create(vals_list)

    def action_assess(self):
        for rec in self:
            rec.state = 'assessment'

    def action_approve(self):
        for rec in self:
            rec.state = 'approved'

    def action_reject(self):
        for rec in self:
            rec.state = 'rejected'

    def action_implement(self):
        for rec in self:
            rec.state = 'implementing'

    def action_done(self):
        for rec in self:
            rec.write({
                'state': 'done',
                'completion_date': fields.Date.today(),
            })
