# -*- coding: utf-8 -*-
"""
Role Line Models - must be loaded before the wizards that use them.

The line model used to expose ``has_accounts`` / ``has_ldap_com_group``
/ ``has_ldap_sec_group`` / ``has_odoo_group`` per BRSO. Those flags
moved to the **target org** (``has_comgroup`` / ``has_secgroup`` /
``has_accounts``) — single source of truth across the codebase. The
line model is now a pure mirror of the BRSO mapping, with sync of
``is_master`` / ``automatic_sync`` only.
"""

from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)

_SYNC_FIELDS = {'is_master', 'automatic_sync'}


class OrgRoleLine(models.TransientModel):
    """Line model for org role wizard."""
    _name = 'myschool.org.role.line'
    _description = 'Organization Role Line'

    wizard_id = fields.Many2one('myschool.manage.org.roles.wizard', string='Wizard', ondelete='cascade')
    proprelation_id = fields.Many2one('myschool.proprelation', string='Relation')
    role_name = fields.Char(string='Role')
    role_label = fields.Char(string='Label')
    is_active = fields.Boolean(string='Active', default=True)
    is_master = fields.Boolean(string='Is Master', default=False)
    automatic_sync = fields.Boolean(string='Auto Sync', default=True)

    def write(self, vals):
        res = super().write(vals)
        proprel_vals = {k: vals[k] for k in _SYNC_FIELDS if k in vals}
        if proprel_vals:
            service = self.env['myschool.manual.task.service']
            for line in self:
                if line.proprelation_id:
                    service.create_manual_task('PROPRELATION', 'UPD', {
                        'proprelation_id': line.proprelation_id.id,
                        'vals': proprel_vals,
                    })
        return res

    def action_remove(self):
        """Deactivate this role-org mapping (BRSO). Group/account
        flags now live on the target org and are managed there."""
        self.ensure_one()
        proprelation = self.proprelation_id
        if proprelation:
            service = self.env['myschool.manual.task.service']
            service.create_manual_task('PROPRELATION', 'DEACT', {
                'proprelation_ids': [proprelation.id],
            })

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
    school_name = fields.Char(string='School')
    is_active = fields.Boolean(string='Active', default=True)
    is_master = fields.Boolean(string='Is Master', default=False)
    automatic_sync = fields.Boolean(string='Auto Sync', default=True)

    def write(self, vals):
        res = super().write(vals)
        proprel_vals = {k: vals[k] for k in _SYNC_FIELDS if k in vals}
        if proprel_vals:
            service = self.env['myschool.manual.task.service']
            for line in self:
                if line.proprelation_id:
                    service.create_manual_task('PROPRELATION', 'UPD', {
                        'proprelation_id': line.proprelation_id.id,
                        'vals': proprel_vals,
                    })
        return res

    def action_remove(self):
        """Remove (deactivate) this role relation."""
        self.ensure_one()
        proprelation = self.proprelation_id
        if proprelation:
            service = self.env['myschool.manual.task.service']
            service.create_manual_task('PROPRELATION', 'DEACT', {
                'proprelation_ids': [proprelation.id],
            })

        # Reopen wizard with saved records via action_open
        person = proprelation.id_person if proprelation else False
        Wizard = self.env['myschool.manage.person.roles.wizard']
        return Wizard.action_open(
            person.id if person else False,
            person.name if person else '',
        )
