from odoo import models, fields

class ConfigItem(models.Model):
    _name = 'myschool.config.item'
    _description = 'Myschool Config Item'

    scope = fields.Char(string="Scope")
    type = fields.Char(string="Type")
    name = fields.Char(string="Name", required=True)

    string_value = fields.Char(string="String Value")
    integer_value = fields.Integer(string="Integer Value")
    boolean_value = fields.Boolean(string="Boolean Value")
