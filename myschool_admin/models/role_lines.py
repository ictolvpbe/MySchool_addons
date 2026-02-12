# -*- coding: utf-8 -*-
"""
Role Line Models - must be loaded before the wizards that use them
"""

from odoo import models, fields


class OrgRoleLine(models.TransientModel):
    """Line model for org role wizard."""
    _name = 'myschool.org.role.line'
    _description = 'Organization Role Line'

    wizard_id = fields.Many2one('myschool.manage.org.roles.wizard', string='Wizard', ondelete='cascade')
    proprelation_id = fields.Many2one('myschool.proprelation', string='Relation')
    role_name = fields.Char(string='Role')
    is_active = fields.Boolean(string='Active', default=True)

    def action_remove(self):
        """Remove (deactivate) this role relation."""
        self.ensure_one()
        proprelation = self.proprelation_id
        if proprelation:
            proprelation.write({'is_active': False})

        # Reopen wizard with saved records via action_open
        org = proprelation.id_org if proprelation else False
        Wizard = self.env['myschool.manage.org.roles.wizard']
        return Wizard.action_open(
            org.id if org else False,
            org.name if org else '',
        )


class PersonRoleLine(models.TransientModel):
    """Line model for person role wizard."""
    _name = 'myschool.person.role.line'
    _description = 'Person Role Line'

    wizard_id = fields.Many2one('myschool.manage.person.roles.wizard', string='Wizard', ondelete='cascade')
    proprelation_id = fields.Many2one('myschool.proprelation', string='Relation')
    role_name = fields.Char(string='Role')
    is_active = fields.Boolean(string='Active', default=True)

    def action_remove(self):
        """Remove (deactivate) this role relation."""
        self.ensure_one()
        proprelation = self.proprelation_id
        if proprelation:
            proprelation.write({'is_active': False})

        # Reopen wizard with saved records via action_open
        person = proprelation.id_person if proprelation else False
        Wizard = self.env['myschool.manage.person.roles.wizard']
        return Wizard.action_open(
            person.id if person else False,
            person.name if person else '',
        )
