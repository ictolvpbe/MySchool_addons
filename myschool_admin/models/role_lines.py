# -*- coding: utf-8 -*-
"""
Role Line Models - must be loaded before the wizards that use them
"""

from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)

# Fields that are written through to the underlying proprelation
_SYNC_FIELDS = {'is_master', 'automatic_sync', 'has_accounts', 'has_ldap_com_group', 'has_ldap_sec_group', 'has_odoo_group'}

# has_* fields that trigger group/person/persongroup sync
_HAS_FIELDS = {'has_accounts', 'has_ldap_com_group', 'has_ldap_sec_group', 'has_odoo_group'}


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
    has_accounts = fields.Boolean(string='Accounts', default=False)
    has_ldap_com_group = fields.Boolean(string='LDAP COM Group', default=False)
    has_ldap_sec_group = fields.Boolean(string='LDAP SEC Group', default=False)
    has_odoo_group = fields.Boolean(string='Odoo Group', default=False)

    def write(self, vals):
        # Capture old has_* values before write
        has_changes = {k: vals[k] for k in _HAS_FIELDS if k in vals}
        old_has = {}
        if has_changes:
            for line in self:
                if line.proprelation_id:
                    old_has[line.id] = {k: getattr(line, k) for k in has_changes}

        res = super().write(vals)

        # Sync changed fields to proprelation via betask
        proprel_vals = {k: vals[k] for k in _SYNC_FIELDS if k in vals}
        if proprel_vals:
            service = self.env['myschool.manual.task.service']
            for line in self:
                if line.proprelation_id:
                    service.create_manual_task('PROPRELATION', 'UPD', {
                        'proprelation_id': line.proprelation_id.id,
                        'vals': proprel_vals,
                    })

        # Process has_* changes: create/remove groups, sync persons & persongroups
        if has_changes:
            processor = self.env['myschool.betask.processor']
            for line in self:
                rel = line.proprelation_id
                if not rel:
                    continue
                old = old_has.get(line.id, {})

                # Flags that were enabled (False → True)
                enabled = {k: True for k, v in has_changes.items() if v and not old.get(k)}
                # Flags that were disabled (True → False)
                disabled = {k: True for k, v in has_changes.items() if not v and old.get(k)}

                if enabled:
                    processor._process_brso_groups(rel, enabled)
                if disabled:
                    processor._remove_brso_groups(rel, disabled)

        return res

    def action_remove(self):
        """Remove (deactivate) this role relation and clean up groups."""
        self.ensure_one()
        proprelation = self.proprelation_id
        if proprelation:
            processor = self.env['myschool.betask.processor']

            # Remove persons from all groups that were enabled on this BRSO
            active_flags = {k: True for k in _HAS_FIELDS if getattr(proprelation, k, False)}
            if active_flags:
                processor._remove_brso_groups(proprelation, active_flags)

            # Deactivate the BRSO
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
