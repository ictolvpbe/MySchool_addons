from odoo import models, fields


class KnowledgeTag(models.Model):
    _name = 'myschool.knowledge.tag'
    _description = 'Knowledge Tag'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    color = fields.Integer(string='Color')
