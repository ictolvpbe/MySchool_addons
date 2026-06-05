from odoo import models, fields


class MyschoolProjectMembership(models.Model):
    """Rol van een gebruiker op een project: eigenaar / bewerker / lezer.

    Eén rol per gebruiker per project. Bepaalt — samen met ``responsible_id``
    — wie een project (en zijn work items) mag zien en bewerken via de
    record rules.
    """

    _name = 'myschool.project.membership'
    _description = 'Project Membership'
    _order = 'role, id'

    project_id = fields.Many2one(
        'myschool.project', string='Project', required=True,
        ondelete='cascade', index=True)
    user_id = fields.Many2one(
        'res.users', string='User', required=True, index=True)
    role = fields.Selection([
        ('owner', 'Owner'),
        ('editor', 'Editor'),
        ('reader', 'Reader'),
    ], string='Role', default='editor', required=True,
        help='Owner/Editor mogen het project en zijn work items bewerken; '
             'Reader heeft alleen-lezen toegang.')

    _unique_user = models.Constraint(
        'UNIQUE(project_id, user_id)',
        'Een gebruiker kan maar één rol per project hebben.')
