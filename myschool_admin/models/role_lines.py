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
        if self.proprelation_id:
            self.proprelation_id.write({'is_active': False})
        
        # Reopen wizard to show updated list
        wizard = self.wizard_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.manage.org.roles.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_org_id': wizard.org_id.id if wizard.org_id else False,
                'default_org_name': wizard.org_name,
            },
        }


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
        if self.proprelation_id:
            self.proprelation_id.write({'is_active': False})
        
        # Reopen wizard to show updated list
        wizard = self.wizard_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.manage.person.roles.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_person_id': wizard.person_id.id if wizard.person_id else False,
                'default_person_name': wizard.person_name,
            },
        }
