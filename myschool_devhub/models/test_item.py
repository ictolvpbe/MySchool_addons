from odoo import models, fields, api


class DevhubTestItem(models.Model):
    _name = 'devhub.test.item'
    _description = 'DevHub Test Item (3T)'
    _order = 'sequence, id desc'

    name = fields.Char(required=True)
    description = fields.Html()
    project_id = fields.Many2one('devhub.project', required=True, ondelete='cascade')
    item_id = fields.Many2one(
        'devhub.item', string='User Story',
        domain="[('project_id', '=', project_id), ('item_type', '=', 'story')]",
    )
    test_type_id = fields.Many2one('devhub.test.type', string='Test Type')
    module_id = fields.Many2one('ir.module.module', string='Module')
    view_name = fields.Char(string='View XML ID')
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
