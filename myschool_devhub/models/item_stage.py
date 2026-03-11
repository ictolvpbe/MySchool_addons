from odoo import models, fields


class DevhubItemStage(models.Model):
    _name = 'devhub.item.stage'
    _description = 'DevHub Item Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Folded in Kanban')
    is_done = fields.Boolean(string='Is Done Stage')
    is_cancelled = fields.Boolean(string='Is Cancelled Stage')
    description = fields.Text()
