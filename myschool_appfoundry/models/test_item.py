import re

from odoo import models, fields, api


class AppfoundryTestItem(models.Model):
    _name = 'appfoundry.test.item'
    _description = 'AppFoundry Test Item (3T)'
    _order = 'sequence, id desc'

    name = fields.Char(required=True)
    description = fields.Html()
    project_id = fields.Many2one('appfoundry.project', required=True, ondelete='cascade')
    item_id = fields.Many2one(
        'appfoundry.item', string='User Story',
        domain="[('project_id', '=', project_id), ('item_type', '=', 'story')]",
    )
    test_type_id = fields.Many2one('appfoundry.test.type', string='Test Type')
    module_id = fields.Many2one('ir.module.module', string='Module')
    view_name = fields.Char(string='View XML ID')
    view_display_name = fields.Char(string='View', compute='_compute_view_display_name',
                                     store=True)
    element_info = fields.Char(string='Element Info')
    state = fields.Selection([
        ('not_tested', 'Not Tested'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('blocked', 'Blocked'),
    ], default='not_tested', required=True)
    tester_id = fields.Many2one('res.users', string='Tester')
    test_date = fields.Datetime(string='Test Date')
    notes = fields.Text()
    source = fields.Selection([
        ('manual', 'Manual'),
        ('auto', 'Auto'),
    ], default='manual', required=True)
    sequence = fields.Integer(default=10)
    is_active = fields.Boolean(default=True)

    @api.depends('view_name')
    def _compute_view_display_name(self):
        for rec in self:
            name = rec.view_name or ''
            # Strip module prefix (e.g. "myschool_admin.some_view" → "some_view")
            if '.' in name:
                name = name.split('.', 1)[1]
            # Convert underscores to spaces and title-case for readability
            name = re.sub(r'_', ' ', name).strip().title()
            rec.view_display_name = name

    def action_pass(self):
        self.write({
            'state': 'passed',
            'tester_id': self.env.uid,
            'test_date': fields.Datetime.now(),
        })

    def action_fail(self):
        self.write({
            'state': 'failed',
            'tester_id': self.env.uid,
            'test_date': fields.Datetime.now(),
        })

    def action_block(self):
        self.write({
            'state': 'blocked',
            'tester_id': self.env.uid,
            'test_date': fields.Datetime.now(),
        })

    def action_reset(self):
        self.write({
            'state': 'not_tested',
            'tester_id': False,
            'test_date': False,
        })
