from odoo import models, fields


class MyschoolProcessField(models.Model):
    _name = 'myschool.process.field'
    _description = 'Myschool Process Field'
    _order = 'sequence, id'

    step_id = fields.Many2one('myschool.process.step', string='Step',
                              required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)

    # Basic
    name = fields.Char(string='Field Name', required=True)
    field_description = fields.Char(string='Label')
    ttype = fields.Selection([
        ('char', 'Char'), ('text', 'Text'), ('html', 'Html'),
        ('integer', 'Integer'), ('float', 'Float'), ('monetary', 'Monetary'),
        ('boolean', 'Boolean'), ('date', 'Date'), ('datetime', 'Datetime'),
        ('selection', 'Selection'),
        ('many2one', 'Many2one'), ('one2many', 'One2many'), ('many2many', 'Many2many'),
        ('binary', 'Binary'), ('image', 'Image'),
    ], string='Type', required=True, default='char')
    required = fields.Boolean(string='Required', default=False)
    readonly = fields.Boolean(string='Readonly', default=False)
    store = fields.Boolean(string='Stored', default=True)
    index = fields.Selection([
        ('', 'None'),
        ('btree', 'BTree'),
        ('btree_not_null', 'BTree Not Null'),
        ('trigram', 'Trigram'),
    ], string='Index', default='')
    copy = fields.Boolean(string='Copy on Duplicate', default=True)
    translate = fields.Boolean(string='Translatable', default=False)

    # Relational
    relation = fields.Char(string='Related Model')
    relation_field = fields.Char(string='Inverse Field')
    relation_table = fields.Char(string='Relation Table')
    domain = fields.Char(string='Domain', default='[]')
    on_delete = fields.Selection([
        ('cascade', 'Cascade'),
        ('set null', 'Set Null'),
        ('restrict', 'Restrict'),
    ], string='On Delete', default='set null')

    # UI
    help_text = fields.Text(string='Help Tooltip')
    groups = fields.Char(string='Groups')

    # Type-specific
    size = fields.Integer(string='Max Size')
    digits = fields.Char(string='Digits')
    selection_values = fields.Text(string='Selection Values',
                                   help='JSON array: [["key","label"],...]')
    default_value = fields.Char(string='Default Value')

    # Source tracking
    source_model = fields.Char(string='Source Model')
