from odoo import models, fields


class ItsmCi(models.Model):
    _name = 'itsm.ci'
    _description = 'ITSM Configuration Item'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    ci_type = fields.Selection(
        [
            ('server', 'Server'),
            ('workstation', 'Workstation'),
            ('network_device', 'Network Device'),
            ('application', 'Application'),
            ('database', 'Database'),
            ('service', 'Service'),
            ('other', 'Other'),
        ],
        string='CI Type',
        required=True,
    )
    description = fields.Text(string='Description')
    state = fields.Selection(
        [
            ('active', 'Active'),
            ('maintenance', 'Maintenance'),
            ('retired', 'Retired'),
        ],
        string='State',
        default='active',
    )
    asset_id = fields.Many2one('myschool.asset', string='Linked Asset')
    service_ids = fields.Many2many('itsm.service', string='Services')
    owner_id = fields.Many2one('res.users', string='Owner')
    environment = fields.Selection(
        [
            ('production', 'Production'),
            ('staging', 'Staging'),
            ('development', 'Development'),
            ('test', 'Test'),
        ],
        string='Environment',
    )
    ip_address = fields.Char(string='IP Address')
    hostname = fields.Char(string='Hostname')
    version = fields.Char(string='Version')
    org_id = fields.Many2one('myschool.org', string='Organization')
    relationship_ids = fields.One2many(
        'itsm.ci.relationship', 'source_ci_id', string='Relationships',
    )
    reverse_relationship_ids = fields.One2many(
        'itsm.ci.relationship', 'target_ci_id', string='Reverse Relationships',
    )


class ItsmCiRelationship(models.Model):
    _name = 'itsm.ci.relationship'
    _description = 'ITSM CI Relationship'

    source_ci_id = fields.Many2one(
        'itsm.ci', string='Source CI', required=True, ondelete='cascade',
    )
    target_ci_id = fields.Many2one(
        'itsm.ci', string='Target CI', required=True, ondelete='cascade',
    )
    relationship_type = fields.Selection(
        [
            ('depends_on', 'Depends On'),
            ('runs_on', 'Runs On'),
            ('connected_to', 'Connected To'),
            ('part_of', 'Part Of'),
            ('used_by', 'Used By'),
        ],
        string='Relationship Type',
        required=True,
    )

    _no_self_relationship = models.Constraint(
        'CHECK(source_ci_id != target_ci_id)',
        'A CI cannot have a relationship with itself.',
    )
