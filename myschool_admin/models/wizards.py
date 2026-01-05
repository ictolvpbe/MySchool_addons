# -*- coding: utf-8 -*-
"""
Object Browser Wizards
======================
Wizards for add, move, and bulk operations.
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CreatePersonWizard(models.TransientModel):
    """Wizard to create a new person and add to an organization."""
    _name = 'myschool.create.person.wizard'
    _description = 'Create Person'

    # Context
    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization Name', readonly=True)
    org_fqdn = fields.Char(string='Organization FQDN', readonly=True, 
        help='OU FQDN Internal of the parent organization')
    external_domain = fields.Char(string='External Domain', readonly=True,
        help='External domain for email generation')
    
    # Person fields
    first_name = fields.Char(string='First Name', required=True)
    last_name = fields.Char(string='Last Name', required=True)
    email_cloud = fields.Char(string='Email Cloud', 
        compute='_compute_email_cloud', store=False, readonly=False,
        help='Auto-generated cloud email address')
    
    # Employee-specific fields
    is_employee = fields.Boolean(string='Is Employee', compute='_compute_is_employee', store=False)
    abbreviation = fields.Char(string='Abbreviation', 
        help='Short abbreviation for the employee')
    stamboeknummer = fields.Char(string='Stamboeknummer',
        help='SAF reference number')
    
    # Role assignment
    role_id = fields.Many2one('myschool.role', string='Role')
    
    # Odoo user linking
    create_odoo_user = fields.Boolean(string='Create Odoo User', default=False,
        help='Create a linked Odoo user account for this person')
    odoo_user_login = fields.Char(string='Login', 
        help='Leave empty to use email as login')
    link_existing_user = fields.Boolean(string='Link Existing User', default=False)
    existing_user_id = fields.Many2one('res.users', string='Existing Odoo User',
        help='Link to an existing Odoo user instead of creating new')

    @api.model
    def default_get(self, fields_list):
        """Set defaults including FQDN from parent org."""
        res = super().default_get(fields_list)
        
        if 'org_id' in res and res['org_id']:
            org = self.env['myschool.org'].browse(res['org_id'])
            if org.exists():
                res['org_name'] = org.name
                # Get ou_fqdn_internal from parent org
                parent_org = self._get_parent_org_static(org)
                if parent_org and hasattr(parent_org, 'ou_fqdn_internal') and parent_org.ou_fqdn_internal:
                    res['org_fqdn'] = parent_org.ou_fqdn_internal
                elif hasattr(org, 'ou_fqdn_internal') and org.ou_fqdn_internal:
                    res['org_fqdn'] = org.ou_fqdn_internal
                
                # Get external_domain for email generation
                ext_domain = self._get_external_domain_static(org)
                if ext_domain:
                    res['external_domain'] = ext_domain
        
        return res

    def _get_parent_org_static(self, org):
        """Get parent org via proprelation (static method for default_get)."""
        if not org:
            return None
        
        PropRelation = self.env.get('myschool.proprelation')
        if PropRelation:
            parent_rel = PropRelation.search([
                ('id_org', '=', org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
            if parent_rel and parent_rel.id_org_parent:
                return parent_rel.id_org_parent
        return None

    def _get_external_domain_static(self, org):
        """Walk up the org hierarchy to find external_domain value."""
        if not org:
            return None
        
        visited = set()
        current_org = org
        
        while current_org and current_org.id not in visited:
            visited.add(current_org.id)
            
            # Check if this org has external_domain
            if hasattr(current_org, 'external_domain') and current_org.external_domain:
                return current_org.external_domain
            
            # Try to find parent org via proprelation
            current_org = self._get_parent_org_static(current_org)
            if not current_org:
                break
        
        return None

    def _remove_diacritics(self, text):
        """Remove diacritic characters and replace with normal variants."""
        import unicodedata
        if not text:
            return ''
        # Normalize to decomposed form (NFD), then filter out combining characters
        normalized = unicodedata.normalize('NFD', text)
        # Remove combining diacritical marks
        result = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
        return result

    @api.depends('first_name', 'last_name', 'external_domain')
    def _compute_email_cloud(self):
        """Compute email_cloud dynamically based on names and domain."""
        for wizard in self:
            if wizard.first_name and wizard.last_name and wizard.external_domain:
                # Clean names: remove diacritics and spaces, lowercase
                clean_first = wizard._remove_diacritics(wizard.first_name).replace(' ', '').lower()
                clean_last = wizard._remove_diacritics(wizard.last_name).replace(' ', '').lower()
                wizard.email_cloud = f"{clean_first}.{clean_last}@{wizard.external_domain}"
            else:
                wizard.email_cloud = ''

    @api.depends('role_id')
    def _compute_is_employee(self):
        """Check if selected role is EMPLOYEE."""
        for wizard in self:
            if wizard.role_id:
                role_name = wizard.role_id.name.upper() if wizard.role_id.name else ''
                shortname = wizard.role_id.shortname.upper() if hasattr(wizard.role_id, 'shortname') and wizard.role_id.shortname else ''
                wizard.is_employee = (role_name == 'EMPLOYEE' or shortname == 'EMPLOYEE')
            else:
                wizard.is_employee = False

    @api.onchange('role_id')
    def _onchange_role_id(self):
        """Auto-enable Odoo user creation for EMPLOYEE role."""
        if self.is_employee:
            self.create_odoo_user = True

    @api.onchange('email_cloud')
    def _onchange_email_cloud(self):
        """Default login to email_cloud."""
        if self.email_cloud and not self.odoo_user_login:
            self.odoo_user_login = self.email_cloud

    @api.onchange('link_existing_user')
    def _onchange_link_existing_user(self):
        """Clear create_odoo_user if linking existing."""
        if self.link_existing_user:
            self.create_odoo_user = False

    @api.onchange('create_odoo_user')
    def _onchange_create_odoo_user(self):
        """Clear link_existing_user if creating new."""
        if self.create_odoo_user:
            self.link_existing_user = False

    def action_create(self):
        """Create the person and optionally link/create Odoo user."""
        self.ensure_one()
        
        Person = self.env['myschool.person']
        PropRelation = self.env['myschool.proprelation']
        
        # Prepare person values
        person_vals = {
            'first_name': self.first_name,
            'name': self.last_name,
            'is_active': True,
        }
        
        # Store email_cloud
        if self.email_cloud and 'email_cloud' in Person._fields:
            person_vals['email_cloud'] = self.email_cloud
        
        # Store employee-specific fields
        if self.is_employee:
            if self.abbreviation and 'abbreviation' in Person._fields:
                person_vals['abbreviation'] = self.abbreviation
            if self.stamboeknummer and 'stamboeknummer' in Person._fields:
                person_vals['stamboeknummer'] = self.stamboeknummer
        
        # Handle Odoo user linking/creation
        user = None
        if self.link_existing_user and self.existing_user_id:
            user = self.existing_user_id
        elif self.create_odoo_user:
            # Create new Odoo user
            login = self.odoo_user_login or self.email_cloud
            if not login:
                raise UserError("Login or email is required to create Odoo user")
            
            # Check if login already exists
            existing_user = self.env['res.users'].search([('login', '=', login)], limit=1)
            if existing_user:
                raise UserError(f"A user with login '{login}' already exists")
            
            user = self.env['res.users'].create({
                'name': f"{self.first_name} {self.last_name}",
                'login': login,
                'email': self.email_cloud or login,
            })
        
        # Link user if available
        if user and 'user_id' in Person._fields:
            person_vals['user_id'] = user.id
        
        # Create person
        person = Person.create(person_vals)
        
        # Create proprelation to org
        proprel_vals = {
            'id_person': person.id,
            'id_org': self.org_id.id,
            'is_active': True,
        }
        if self.role_id:
            proprel_vals['id_role'] = self.role_id.id
        
        PropRelation.create(proprel_vals)
        
        _logger.info(f"Created person {person.name} in org {self.org_id.name}")
        
        # Return action to optionally open the person form
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.person',
            'res_id': person.id,
            'views': [[False, 'form']],
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_create_and_close(self):
        """Create person and return to browser."""
        self.ensure_one()
        
        Person = self.env['myschool.person']
        PropRelation = self.env['myschool.proprelation']
        
        # Prepare person values
        person_vals = {
            'first_name': self.first_name,
            'name': self.last_name,
            'is_active': True,
        }
        
        # Store email_cloud
        if self.email_cloud and 'email_cloud' in Person._fields:
            person_vals['email_cloud'] = self.email_cloud
        
        # Store employee-specific fields
        if self.is_employee:
            if self.abbreviation and 'abbreviation' in Person._fields:
                person_vals['abbreviation'] = self.abbreviation
            if self.stamboeknummer and 'stamboeknummer' in Person._fields:
                person_vals['stamboeknummer'] = self.stamboeknummer
        
        # Handle Odoo user
        user = None
        if self.link_existing_user and self.existing_user_id:
            user = self.existing_user_id
        elif self.create_odoo_user:
            login = self.odoo_user_login or self.email_cloud
            if not login:
                raise UserError("Login or email is required to create Odoo user")
            
            existing_user = self.env['res.users'].search([('login', '=', login)], limit=1)
            if existing_user:
                raise UserError(f"A user with login '{login}' already exists")
            
            user = self.env['res.users'].create({
                'name': f"{self.first_name} {self.last_name}",
                'login': login,
                'email': self.email_cloud or login,
            })
        
        if user and 'user_id' in Person._fields:
            person_vals['user_id'] = user.id
        
        person = Person.create(person_vals)
        
        proprel_vals = {
            'id_person': person.id,
            'id_org': self.org_id.id,
            'is_active': True,
        }
        if self.role_id:
            proprel_vals['id_role'] = self.role_id.id
        
        PropRelation.create(proprel_vals)
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class AddChildOrgWizard(models.TransientModel):
    """Wizard to add a child organization."""
    _name = 'myschool.add.child.org.wizard'
    _description = 'Add Child Organization'

    parent_org_id = fields.Many2one('myschool.org', string='Parent Organization', required=True)
    parent_org_name = fields.Char(string='Parent Organization Name', readonly=True)
    
    # Option 1: Select existing org
    use_existing = fields.Boolean(string='Use Existing Organization', default=False)
    existing_org_id = fields.Many2one('myschool.org', string='Existing Organization')
    
    # Option 2: Create new org (default)
    # Required fields
    new_org_name = fields.Char(string='Full Name', required=True)
    new_org_name_short = fields.Char(string='Short Name', required=True,
        help='Short code/abbreviation for the organization')
    new_org_inst_nr = fields.Char(string='Institution Number', required=True,
        help='Official institution number (inherited from parent by default)',
        compute='_compute_inherited_fields', store=True, readonly=False, precompute=True)
    
    # LDAP OU fields - populated by onchange when has_ou is True
    new_org_ou_fqdn_intern = fields.Char(string='OU FQDN Intern',
        help='Internal LDAP OU path (auto-generated from parent)')
    new_org_ou_fqdn_extern = fields.Char(string='OU FQDN Extern',
        help='External LDAP OU path (auto-generated from parent)')
    
    # Communication group name - populated by onchange when has_comgroup is True
    new_org_com_group_name = fields.Char(string='Communication Group Name',
        help='Auto-generated from organization hierarchy (grp-parent1-parent2-...)')
    new_org_com_group_fqdn_internal = fields.Char(string='Com Group FQDN Internal',
        help='CN=com_group_name,ou_fqdn_internal')
    new_org_com_group_fqdn_external = fields.Char(string='Com Group FQDN External',
        help='CN=com_group_name,ou_fqdn_external')
    
    # Security group name - populated by onchange when has_secgroup is True
    new_org_sec_group_name = fields.Char(string='Security Group Name',
        help='Auto-generated from organization hierarchy (bgrp-parent1-parent2-...)')
    new_org_sec_group_fqdn_internal = fields.Char(string='Sec Group FQDN Internal',
        help='CN=sec_group_name,ou_fqdn_internal')
    new_org_sec_group_fqdn_external = fields.Char(string='Sec Group FQDN External',
        help='CN=sec_group_name,ou_fqdn_external')
    
    # Boolean flags
    new_org_has_ou = fields.Boolean(string='Heeft OU', default=False)
    new_org_has_role = fields.Boolean(string='Heeft Role', default=False)
    new_org_has_comgroup = fields.Boolean(string='Heeft Communicatiegroep', default=False)
    new_org_has_secgroup = fields.Boolean(string='Heeft Securitygroep', default=False)
    
    @api.model
    def default_get(self, fields_list):
        """Set default values including parent_org_name and OU FQDN fields."""
        res = super().default_get(fields_list)
        if 'parent_org_id' in res and res['parent_org_id']:
            parent = self.env['myschool.org'].browse(res['parent_org_id'])
            if parent.exists():
                res['parent_org_name'] = parent.name
                
                # Initialize OU FQDN fields with placeholder (lowercase)
                ou_prefix = "ou=new,"
                
                if hasattr(parent, 'ou_fqdn_internal') and parent.ou_fqdn_internal:
                    res['new_org_ou_fqdn_intern'] = ou_prefix + parent.ou_fqdn_internal.lower()
                else:
                    res['new_org_ou_fqdn_intern'] = ou_prefix
                
                if hasattr(parent, 'ou_fqdn_external') and parent.ou_fqdn_external:
                    res['new_org_ou_fqdn_extern'] = ou_prefix + parent.ou_fqdn_external.lower()
                else:
                    res['new_org_ou_fqdn_extern'] = ou_prefix
        return res
    
    # Optional fields
    new_org_type_id = fields.Many2one('myschool.org.type', string='Organization Type')
    new_org_description = fields.Text(string='Description')

    @api.depends('parent_org_id')
    def _compute_inherited_fields(self):
        """Auto-inherit fields from parent organization."""
        for wizard in self:
            if wizard.parent_org_id:
                parent = wizard.parent_org_id
                
                # Set parent name for display
                wizard.parent_org_name = parent.name
                
                # Inherit inst_nr
                if hasattr(parent, 'inst_nr') and parent.inst_nr:
                    wizard.new_org_inst_nr = parent.inst_nr
                else:
                    wizard.new_org_inst_nr = False
            else:
                wizard.parent_org_name = False
                wizard.new_org_inst_nr = False
    
    @api.onchange('parent_org_id')
    def _onchange_parent_org_id(self):
        """Initialize OU FQDN fields when parent is set."""
        if self.parent_org_id:
            parent = self.parent_org_id
            short_name = (self.new_org_name_short or 'new').lower()
            ou_prefix = f"ou={short_name},"
            
            # OU FQDN Internal (lowercase)
            if hasattr(parent, 'ou_fqdn_internal') and parent.ou_fqdn_internal:
                self.new_org_ou_fqdn_intern = ou_prefix + parent.ou_fqdn_internal.lower()
            else:
                self.new_org_ou_fqdn_intern = ou_prefix
            
            # OU FQDN External (lowercase)
            if hasattr(parent, 'ou_fqdn_external') and parent.ou_fqdn_external:
                self.new_org_ou_fqdn_extern = ou_prefix + parent.ou_fqdn_external.lower()
            else:
                self.new_org_ou_fqdn_extern = ou_prefix
    
    def _build_group_name(self, prefix='grp-'):
        """Build group name from org hierarchy.
        
        Format: <prefix><name_short>-<parent_short>-<grandparent_short>-...
        Excludes: is_administrative=True orgs and orgs with type 'SCHOOLBOARD'
        
        Args:
            prefix: 'grp-' for communication group, 'bgrp-' for security group
        """
        self.ensure_one()
        
        parts = []
        
        # Add current org's name_short
        if self.new_org_name_short:
            parts.append(self.new_org_name_short.lower())
        
        # Walk up the parent chain
        PropRelation = self.env['myschool.proprelation']
        current_org = self.parent_org_id
        visited = set()
        
        while current_org and current_org.id not in visited:
            visited.add(current_org.id)
            
            # Check if this org should be excluded
            should_exclude = False
            
            # Exclude if is_administrative is True
            if hasattr(current_org, 'is_administrative') and current_org.is_administrative:
                should_exclude = True
            
            # Exclude if org_type is SCHOOLBOARD
            if hasattr(current_org, 'org_type_id') and current_org.org_type_id:
                if current_org.org_type_id.name == 'SCHOOLBOARD':
                    should_exclude = True
            
            # Add to parts if not excluded
            if not should_exclude:
                short_name = current_org.name_short if hasattr(current_org, 'name_short') and current_org.name_short else current_org.name
                if short_name:
                    parts.append(short_name.lower())
            
            # Find parent via proprelation
            parent_rel = PropRelation.search([
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
            if parent_rel and parent_rel.id_org_parent:
                current_org = parent_rel.id_org_parent
            else:
                break
        
        if parts:
            return prefix + '-'.join(parts)
        return False

    @api.onchange('new_org_name_short')
    def _onchange_name_short_update_fqdn(self):
        """Update OU FQDN and group names when short name changes."""
        if self.parent_org_id and self.new_org_name_short:
            parent = self.parent_org_id
            # Make OU prefix lowercase
            ou_prefix = f"ou={self.new_org_name_short.lower()},"
            
            # Always update OU FQDN fields (regardless of has_ou flag)
            # OU FQDN Internal - all lowercase
            if hasattr(parent, 'ou_fqdn_internal') and parent.ou_fqdn_internal:
                self.new_org_ou_fqdn_intern = ou_prefix + parent.ou_fqdn_internal.lower()
            else:
                self.new_org_ou_fqdn_intern = ou_prefix
            
            # OU FQDN External - all lowercase
            if hasattr(parent, 'ou_fqdn_external') and parent.ou_fqdn_external:
                self.new_org_ou_fqdn_extern = ou_prefix + parent.ou_fqdn_external.lower()
            else:
                self.new_org_ou_fqdn_extern = ou_prefix
            
            # Update com_group_name and FQDNs only if has_comgroup is True
            if self.new_org_has_comgroup:
                self.new_org_com_group_name = self._build_group_name('grp-')
                self._update_com_group_fqdns()
            
            # Update sec_group_name and FQDNs only if has_secgroup is True
            if self.new_org_has_secgroup:
                self.new_org_sec_group_name = self._build_group_name('bgrp-')
                self._update_sec_group_fqdns()
    
    @api.onchange('new_org_has_ou')
    def _onchange_has_ou(self):
        """Recalculate group FQDNs when has_ou checkbox changes."""
        # OU FQDN fields are always calculated, but group FQDNs depend on them
        if self.new_org_has_ou:
            # Recalculate group FQDNs if groups are enabled
            if self.new_org_has_comgroup:
                self._update_com_group_fqdns()
            if self.new_org_has_secgroup:
                self._update_sec_group_fqdns()
    
    @api.onchange('new_org_has_comgroup')
    def _onchange_has_comgroup(self):
        """Update com_group_name and FQDNs when has_comgroup checkbox changes."""
        if self.new_org_has_comgroup and self.parent_org_id:
            # First calculate the group name
            self.new_org_com_group_name = self._build_group_name('grp-')
            # Then calculate FQDNs based on group name and OU paths
            self._update_com_group_fqdns()
        else:
            self.new_org_com_group_name = False
            self.new_org_com_group_fqdn_internal = False
            self.new_org_com_group_fqdn_external = False
    
    def _get_ou_for_groups(self):
        """Get the OuForGroups CI value from the organization hierarchy.
        
        Searches for a CI named 'OuForGroups' linked to the parent org or its ancestors.
        Returns the string value (e.g., 'grp') or None if not found.
        """
        if not self.parent_org_id:
            return None
        
        # Check if CI models exist
        if 'myschool.config.item' not in self.env:
            return None
        
        ConfigItem = self.env['myschool.config.item']
        
        # Try to get via ConfigItem's method if available
        if hasattr(ConfigItem, 'get_ci_value_by_org_and_name'):
            parent_short = self.parent_org_id.name_short if hasattr(self.parent_org_id, 'name_short') else self.parent_org_id.name
            value = ConfigItem.get_ci_value_by_org_and_name(parent_short, 'OuForGroups')
            if value:
                return value
        
        # Fallback: search directly in CiRelation
        if 'myschool.ci.relation' in self.env:
            CiRelation = self.env['myschool.ci.relation']
            
            # Walk up the org hierarchy to find the CI
            current_org = self.parent_org_id
            PropRelation = self.env.get('myschool.proprelation')
            visited = set()
            
            while current_org and current_org.id not in visited:
                visited.add(current_org.id)
                
                # Search for OuForGroups CI linked to this org
                ci_relation = CiRelation.search([
                    ('id_org', '=', current_org.id),
                    ('id_ci.name', '=', 'OuForGroups'),
                    ('isactive', '=', True)
                ], limit=1)
                
                if ci_relation and ci_relation.id_ci and ci_relation.id_ci.string_value:
                    return ci_relation.id_ci.string_value
                
                # Move to parent org
                if PropRelation:
                    parent_rel = PropRelation.search([
                        ('id_org', '=', current_org.id),
                        ('id_org_parent', '!=', False),
                        ('is_active', '=', True),
                    ], limit=1)
                    current_org = parent_rel.id_org_parent if parent_rel else None
                else:
                    break
        
        return None
    
    def _update_com_group_fqdns(self):
        """Update communication group FQDNs based on group name and OU paths.
        
        Format: cn={group_name},ou={OuForGroups},{parent_ou_fqdn}
        Example: cn=grp-lkr-bawa,ou=grp,ou=bawa,dc=olvp,dc=test
        
        Note: Groups are placed under the PARENT org's OU, not the new org's OU.
        All values are lowercase.
        """
        if self.new_org_com_group_name and self.parent_org_id:
            group_name = self.new_org_com_group_name.lower()
            ou_for_groups = self._get_ou_for_groups()
            
            # Get parent's OU FQDN (not the new org's)
            parent_ou_internal = ''
            parent_ou_external = ''
            if hasattr(self.parent_org_id, 'ou_fqdn_internal') and self.parent_org_id.ou_fqdn_internal:
                parent_ou_internal = self.parent_org_id.ou_fqdn_internal.lower()
            if hasattr(self.parent_org_id, 'ou_fqdn_external') and self.parent_org_id.ou_fqdn_external:
                parent_ou_external = self.parent_org_id.ou_fqdn_external.lower()
            
            # Build internal FQDN
            if parent_ou_internal:
                if ou_for_groups:
                    self.new_org_com_group_fqdn_internal = f"cn={group_name},ou={ou_for_groups.lower()},{parent_ou_internal}"
                else:
                    self.new_org_com_group_fqdn_internal = f"cn={group_name},{parent_ou_internal}"
            else:
                self.new_org_com_group_fqdn_internal = False
            
            # Build external FQDN
            if parent_ou_external:
                if ou_for_groups:
                    self.new_org_com_group_fqdn_external = f"cn={group_name},ou={ou_for_groups.lower()},{parent_ou_external}"
                else:
                    self.new_org_com_group_fqdn_external = f"cn={group_name},{parent_ou_external}"
            else:
                self.new_org_com_group_fqdn_external = False
        else:
            self.new_org_com_group_fqdn_internal = False
            self.new_org_com_group_fqdn_external = False
    
    @api.onchange('new_org_has_secgroup')
    def _onchange_has_secgroup(self):
        """Update sec_group_name and FQDNs when has_secgroup checkbox changes."""
        if self.new_org_has_secgroup and self.parent_org_id:
            # First calculate the group name
            self.new_org_sec_group_name = self._build_group_name('bgrp-')
            # Then calculate FQDNs based on group name and OU paths
            self._update_sec_group_fqdns()
        else:
            self.new_org_sec_group_name = False
            self.new_org_sec_group_fqdn_internal = False
            self.new_org_sec_group_fqdn_external = False
    
    def _update_sec_group_fqdns(self):
        """Update security group FQDNs based on group name and OU paths.
        
        Format: cn={group_name},ou={OuForGroups},{parent_ou_fqdn}
        Example: cn=bgrp-lkr-bawa,ou=grp,ou=bawa,dc=olvp,dc=test
        
        Note: Groups are placed under the PARENT org's OU, not the new org's OU.
        All values are lowercase.
        """
        if self.new_org_sec_group_name and self.parent_org_id:
            group_name = self.new_org_sec_group_name.lower()
            ou_for_groups = self._get_ou_for_groups()
            
            # Get parent's OU FQDN (not the new org's)
            parent_ou_internal = ''
            parent_ou_external = ''
            if hasattr(self.parent_org_id, 'ou_fqdn_internal') and self.parent_org_id.ou_fqdn_internal:
                parent_ou_internal = self.parent_org_id.ou_fqdn_internal.lower()
            if hasattr(self.parent_org_id, 'ou_fqdn_external') and self.parent_org_id.ou_fqdn_external:
                parent_ou_external = self.parent_org_id.ou_fqdn_external.lower()
            
            # Build internal FQDN
            if parent_ou_internal:
                if ou_for_groups:
                    self.new_org_sec_group_fqdn_internal = f"cn={group_name},ou={ou_for_groups.lower()},{parent_ou_internal}"
                else:
                    self.new_org_sec_group_fqdn_internal = f"cn={group_name},{parent_ou_internal}"
            else:
                self.new_org_sec_group_fqdn_internal = False
            
            # Build external FQDN
            if parent_ou_external:
                if ou_for_groups:
                    self.new_org_sec_group_fqdn_external = f"cn={group_name},ou={ou_for_groups.lower()},{parent_ou_external}"
                else:
                    self.new_org_sec_group_fqdn_external = f"cn={group_name},{parent_ou_external}"
            else:
                self.new_org_sec_group_fqdn_external = False
        else:
            self.new_org_sec_group_fqdn_internal = False
            self.new_org_sec_group_fqdn_external = False

    @api.onchange('new_org_name')
    def _onchange_new_org_name(self):
        """Suggest name_short from name."""
        if self.new_org_name and not self.new_org_name_short:
            # Create abbreviation from first letters of words
            words = self.new_org_name.split()
            if len(words) > 1:
                self.new_org_name_short = ''.join(w[0].upper() for w in words if w)
            else:
                self.new_org_name_short = self.new_org_name[:10].upper()

    def action_add(self):
        """Add the child organization and open it for editing."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        Org = self.env['myschool.org']
        
        if self.use_existing:
            if not self.existing_org_id:
                raise UserError("Please select an existing organization")
            child_org = self.existing_org_id
        else:
            if not self.new_org_name:
                raise UserError("Please enter a name for the new organization")
            if not self.new_org_name_short:
                raise UserError("Please enter a short name for the organization")
            if not self.new_org_inst_nr:
                raise UserError("Please enter an institution number")
            
            # Create new org with required fields
            org_vals = {
                'name': self.new_org_name,
                'name_short': self.new_org_name_short,
                'inst_nr': self.new_org_inst_nr,
                'is_active': True,
            }
            
            # Add OU FQDN fields if present
            if self.new_org_ou_fqdn_intern:
                org_vals['ou_fqdn_internal'] = self.new_org_ou_fqdn_intern
            if self.new_org_ou_fqdn_extern:
                org_vals['ou_fqdn_external'] = self.new_org_ou_fqdn_extern
            
            # Add com_group fields if present
            if self.new_org_com_group_name:
                org_vals['com_group_name'] = self.new_org_com_group_name
            if self.new_org_com_group_fqdn_internal:
                org_vals['com_group_fqdn_internal'] = self.new_org_com_group_fqdn_internal
            if self.new_org_com_group_fqdn_external:
                org_vals['com_group_fqdn_external'] = self.new_org_com_group_fqdn_external
            
            # Add sec_group fields if present
            if self.new_org_sec_group_name:
                org_vals['sec_group_name'] = self.new_org_sec_group_name
            if self.new_org_sec_group_fqdn_internal:
                org_vals['sec_group_fqdn_internal'] = self.new_org_sec_group_fqdn_internal
            if self.new_org_sec_group_fqdn_external:
                org_vals['sec_group_fqdn_external'] = self.new_org_sec_group_fqdn_external
            
            # Add boolean flags
            org_vals['has_ou'] = self.new_org_has_ou
            org_vals['has_role'] = self.new_org_has_role
            org_vals['has_comgroup'] = self.new_org_has_comgroup
            org_vals['has_secgroup'] = self.new_org_has_secgroup
            
            if self.new_org_type_id:
                org_vals['org_type_id'] = self.new_org_type_id.id
            if self.new_org_description and 'description' in Org._fields:
                org_vals['description'] = self.new_org_description
            
            child_org = Org.create(org_vals)
        
        # Check for circular reference
        if child_org.id == self.parent_org_id.id:
            raise UserError("An organization cannot be its own parent")
        
        # Check if already a child
        existing = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '=', self.parent_org_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"{child_org.name} is already a child of {self.parent_org_id.name}")
        
        # Deactivate any existing parent relation
        old_parent = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True),
        ])
        if old_parent:
            old_parent.write({'is_active': False})
        
        # Get or create OrgTree proprelation type
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree_type = PropRelationType.search([('name', '=', 'OrgTree')], limit=1)
        if not org_tree_type:
            org_tree_type = PropRelationType.create({
                'name': 'OrgTree',
                'usage': 'Organization hierarchy relationship',
                'is_active': True,
            })
        
        # Build the relation name: Or=<child_short>.OrP<parent_short>
        child_short = child_org.name_short if hasattr(child_org, 'name_short') and child_org.name_short else child_org.name
        parent_short = self.parent_org_id.name_short if hasattr(self.parent_org_id, 'name_short') and self.parent_org_id.name_short else self.parent_org_id.name
        relation_name = f"Or={child_short}.OrP={parent_short}"
        
        # Create new parent relation
        PropRelation.create({
            'name': relation_name,
            'proprelation_type_id': org_tree_type.id,
            'id_org': child_org.id,
            'id_org_parent': self.parent_org_id.id,
            'is_active': True,
        })
        
        _logger.info(f"Added org {child_org.name} under {self.parent_org_id.name}")
        
        # Open the org form for further editing
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.org',
            'res_id': child_org.id,
            'views': [[False, 'form']],
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_add_and_close(self):
        """Add org and return to browser without opening form."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        Org = self.env['myschool.org']
        
        if self.use_existing:
            if not self.existing_org_id:
                raise UserError("Please select an existing organization")
            child_org = self.existing_org_id
        else:
            if not self.new_org_name:
                raise UserError("Please enter a name for the new organization")
            if not self.new_org_name_short:
                raise UserError("Please enter a short name for the organization")
            if not self.new_org_inst_nr:
                raise UserError("Please enter an institution number")
            
            org_vals = {
                'name': self.new_org_name,
                'name_short': self.new_org_name_short,
                'inst_nr': self.new_org_inst_nr,
                'is_active': True,
            }
            
            # Add OU FQDN fields if present
            if self.new_org_ou_fqdn_intern:
                org_vals['ou_fqdn_internal'] = self.new_org_ou_fqdn_intern
            if self.new_org_ou_fqdn_extern:
                org_vals['ou_fqdn_external'] = self.new_org_ou_fqdn_extern
            
            # Add com_group fields if present
            if self.new_org_com_group_name:
                org_vals['com_group_name'] = self.new_org_com_group_name
            if self.new_org_com_group_fqdn_internal:
                org_vals['com_group_fqdn_internal'] = self.new_org_com_group_fqdn_internal
            if self.new_org_com_group_fqdn_external:
                org_vals['com_group_fqdn_external'] = self.new_org_com_group_fqdn_external
            
            # Add sec_group fields if present
            if self.new_org_sec_group_name:
                org_vals['sec_group_name'] = self.new_org_sec_group_name
            if self.new_org_sec_group_fqdn_internal:
                org_vals['sec_group_fqdn_internal'] = self.new_org_sec_group_fqdn_internal
            if self.new_org_sec_group_fqdn_external:
                org_vals['sec_group_fqdn_external'] = self.new_org_sec_group_fqdn_external
            
            # Add boolean flags
            org_vals['has_ou'] = self.new_org_has_ou
            org_vals['has_role'] = self.new_org_has_role
            org_vals['has_comgroup'] = self.new_org_has_comgroup
            org_vals['has_secgroup'] = self.new_org_has_secgroup
            
            if self.new_org_type_id:
                org_vals['org_type_id'] = self.new_org_type_id.id
            if self.new_org_description and 'description' in Org._fields:
                org_vals['description'] = self.new_org_description
            
            child_org = Org.create(org_vals)
        
        if child_org.id == self.parent_org_id.id:
            raise UserError("An organization cannot be its own parent")
        
        existing = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '=', self.parent_org_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"{child_org.name} is already a child of {self.parent_org_id.name}")
        
        old_parent = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True),
        ])
        if old_parent:
            old_parent.write({'is_active': False})
        
        # Get or create OrgTree proprelation type
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree_type = PropRelationType.search([('name', '=', 'OrgTree')], limit=1)
        if not org_tree_type:
            org_tree_type = PropRelationType.create({
                'name': 'OrgTree',
                'usage': 'Organization hierarchy relationship',
                'is_active': True,
            })
        
        # Build the relation name: Or=<child_short>.OrP<parent_short>
        child_short = child_org.name_short if hasattr(child_org, 'name_short') and child_org.name_short else child_org.name
        parent_short = self.parent_org_id.name_short if hasattr(self.parent_org_id, 'name_short') and self.parent_org_id.name_short else self.parent_org_id.name
        relation_name = f"Or={child_short}.OrP={parent_short}"
        
        PropRelation.create({
            'name': relation_name,
            'proprelation_type_id': org_tree_type.id,
            'id_org': child_org.id,
            'id_org_parent': self.parent_org_id.id,
            'is_active': True,
        })
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class MoveOrgWizard(models.TransientModel):
    """Wizard to move an organization to a new parent."""
    _name = 'myschool.move.org.wizard'
    _description = 'Move Organization'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization Name', readonly=True)
    new_parent_id = fields.Many2one('myschool.org', string='New Parent Organization')
    move_to_root = fields.Boolean(string='Move to Root (no parent)')

    def action_move(self):
        """Move the organization."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        if self.move_to_root:
            # Remove parent relation
            existing = PropRelation.search([
                ('id_org', '=', self.org_id.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ])
            if existing:
                existing.write({'is_active': False})
        else:
            if not self.new_parent_id:
                raise UserError("Please select a new parent organization or check 'Move to Root'")
            
            # Use the object browser method for validation
            self.env['myschool.object.browser'].move_org(self.org_id.id, self.new_parent_id.id)
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class MovePersonWizard(models.TransientModel):
    """Wizard to move a person to a different organization."""
    _name = 'myschool.move.person.wizard'
    _description = 'Move Person to Organization'

    person_id = fields.Many2one('myschool.person', string='Person', required=True)
    person_name = fields.Char(string='Person Name', readonly=True)
    new_org_id = fields.Many2one('myschool.org', string='New Organization', required=True)
    keep_roles = fields.Boolean(string='Keep Existing Roles', default=True)

    def action_move(self):
        """Move the person."""
        self.ensure_one()
        
        self.env['myschool.object.browser'].move_person_to_org(
            self.person_id.id, 
            self.new_org_id.id
        )
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class AssignRoleWizard(models.TransientModel):
    """Wizard to assign a role to a person."""
    _name = 'myschool.assign.role.wizard'
    _description = 'Assign Role to Person'

    person_id = fields.Many2one('myschool.person', string='Person', required=True)
    person_name = fields.Char(string='Person Name', readonly=True)
    role_id = fields.Many2one('myschool.role', string='Role', required=True)
    org_id = fields.Many2one('myschool.org', string='Organization (optional)',
                             help='Assign role in context of this organization')

    def action_assign(self):
        """Assign the role."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        # Check if already exists
        domain = [
            ('id_person', '=', self.person_id.id),
            ('id_role', '=', self.role_id.id),
            ('is_active', '=', True),
        ]
        if self.org_id:
            domain.append(('id_org', '=', self.org_id.id))
        
        existing = PropRelation.search(domain, limit=1)
        
        if existing:
            raise UserError(f"{self.person_id.name} already has role {self.role_id.name}")
        
        vals = {
            'id_person': self.person_id.id,
            'id_role': self.role_id.id,
            'is_active': True,
        }
        if self.org_id:
            vals['id_org'] = self.org_id.id
        
        PropRelation.create(vals)
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class BulkAssignRoleWizard(models.TransientModel):
    """Wizard to assign a role to multiple persons."""
    _name = 'myschool.bulk.assign.role.wizard'
    _description = 'Bulk Assign Role'

    person_ids = fields.Many2many('myschool.person', string='Persons')
    person_count = fields.Integer(string='Number of Persons', readonly=True)
    role_id = fields.Many2one('myschool.role', string='Role', required=True)
    org_id = fields.Many2one('myschool.org', string='Organization (optional)')

    def action_assign(self):
        """Assign role to all selected persons."""
        self.ensure_one()
        
        person_ids = self.person_ids.ids
        if not person_ids:
            # Try to get from context
            person_ids = self.env.context.get('default_person_ids', [])
        
        if not person_ids:
            raise UserError("No persons selected")
        
        count = self.env['myschool.object.browser'].bulk_assign_role(
            person_ids,
            self.role_id.id,
            self.org_id.id if self.org_id else None
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Assigned role to {count} persons',
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }


class BulkMoveWizard(models.TransientModel):
    """Wizard to move multiple persons to an organization."""
    _name = 'myschool.bulk.move.wizard'
    _description = 'Bulk Move Persons'

    person_ids = fields.Many2many('myschool.person', string='Persons')
    person_count = fields.Integer(string='Number of Persons', readonly=True)
    org_id = fields.Many2one('myschool.org', string='Target Organization', required=True)

    def action_move(self):
        """Move all selected persons."""
        self.ensure_one()
        
        person_ids = self.person_ids.ids
        if not person_ids:
            person_ids = self.env.context.get('default_person_ids', [])
        
        if not person_ids:
            raise UserError("No persons selected")
        
        count = self.env['myschool.object.browser'].bulk_move_to_org(
            person_ids,
            self.org_id.id
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Moved {count} persons to {self.org_id.name}',
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }


# =============================================================================
# Configuration Item Wizards
# =============================================================================

class ManageCiRelationsWizard(models.TransientModel):
    """Wizard to manage Configuration Item relations for an organization."""
    _name = 'myschool.manage.ci.relations.wizard'
    _description = 'Manage Configuration Items'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization Name', compute='_compute_org_name')
    ci_relation_count = fields.Integer(compute='_compute_ci_relation_count')
    
    @api.depends('org_id')
    def _compute_org_name(self):
        for wizard in self:
            wizard.org_name = wizard.org_id.name if wizard.org_id else ''
    
    @api.depends('org_id')
    def _compute_ci_relation_count(self):
        CiRelation = self.env['myschool.ci.relation']
        for wizard in self:
            if wizard.org_id:
                wizard.ci_relation_count = CiRelation.search_count([
                    ('id_org', '=', wizard.org_id.id),
                    ('isactive', '=', True)
                ])
            else:
                wizard.ci_relation_count = 0
    
    def action_add_ci(self):
        """Open wizard to add a new CI relation."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.ci.relation.wizard',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_org_id': self.org_id.id,
            },
        }
    
    def action_view_all(self):
        """View all CI relations for this org in a list."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.ci.relation',
            'views': [[False, 'tree'], [False, 'form']],
            'target': 'current',
            'domain': [('id_org', '=', self.org_id.id)],
            'context': {
                'default_id_org': self.org_id.id,
            },
        }


class AddCiRelationWizard(models.TransientModel):
    """Wizard to add a Configuration Item relation to an organization."""
    _name = 'myschool.add.ci.relation.wizard'
    _description = 'Add Configuration Item'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization', compute='_compute_org_name')
    
    # Option 1: Select existing CI
    use_existing_ci = fields.Boolean(string='Use Existing Config Item', default=True)
    existing_ci_id = fields.Many2one('myschool.config.item', string='Config Item',
        domain=[('is_active', '=', True)])
    
    # Option 2: Create new CI
    new_ci_name = fields.Char(string='Name')
    new_ci_scope = fields.Selection([
        ('global', 'Global'),
        ('local', 'Local'),
        ('module', 'Module'),
        ('org', 'Organization'),
        ('user', 'User'),
    ], string="Scope", default='org')
    new_ci_type = fields.Selection([
        ('config', 'Configuration'),
        ('status', 'Status'),
        ('setting', 'Setting'),
        ('parameter', 'Parameter'),
        ('credential', 'Credential'),
        ('api', 'API Setting'),
    ], string="Type", default='config')
    
    # Value fields
    value_type = fields.Selection([
        ('string', 'Text'),
        ('integer', 'Number'),
        ('boolean', 'Yes/No'),
    ], string="Value Type", default='string')
    string_value = fields.Char(string='Text Value')
    integer_value = fields.Integer(string='Number Value')
    boolean_value = fields.Boolean(string='Yes/No Value')
    
    new_ci_description = fields.Text(string='Description')
    
    @api.depends('org_id')
    def _compute_org_name(self):
        for wizard in self:
            wizard.org_name = wizard.org_id.name if wizard.org_id else ''
    
    def action_add(self):
        """Add the CI relation."""
        self.ensure_one()
        
        CiRelation = self.env['myschool.ci.relation']
        ConfigItem = self.env['myschool.config.item']
        
        if self.use_existing_ci:
            if not self.existing_ci_id:
                raise UserError("Please select a Configuration Item")
            config_item = self.existing_ci_id
        else:
            if not self.new_ci_name:
                raise UserError("Please enter a name for the Configuration Item")
            
            # Create new ConfigItem
            ci_vals = {
                'name': self.new_ci_name,
                'scope': self.new_ci_scope,
                'type': self.new_ci_type,
                'is_active': True,
            }
            
            # Set value based on type
            if self.value_type == 'string':
                ci_vals['string_value'] = self.string_value
            elif self.value_type == 'integer':
                ci_vals['integer_value'] = self.integer_value
            elif self.value_type == 'boolean':
                ci_vals['boolean_value'] = self.boolean_value
            
            if self.new_ci_description:
                ci_vals['description'] = self.new_ci_description
            
            config_item = ConfigItem.create(ci_vals)
        
        # Check if relation already exists
        existing = CiRelation.search([
            ('id_org', '=', self.org_id.id),
            ('id_ci', '=', config_item.id),
            ('isactive', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"Configuration Item '{config_item.name}' is already linked to this organization")
        
        # Create the relation
        CiRelation.create({
            'id_org': self.org_id.id,
            'id_ci': config_item.id,
            'isactive': True,
        })
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
    def action_add_and_new(self):
        """Add the CI relation and open wizard for another."""
        self.action_add()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.ci.relation.wizard',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_org_id': self.org_id.id,
            },
        }


class EditCiRelationWizard(models.TransientModel):
    """Wizard to edit a Configuration Item relation value."""
    _name = 'myschool.edit.ci.relation.wizard'
    _description = 'Edit Configuration Item'

    ci_relation_id = fields.Many2one('myschool.ci.relation', string='Relation', required=True)
    ci_name = fields.Char(string='Config Item', readonly=True)
    org_name = fields.Char(string='Organization', readonly=True)
    
    # Value fields
    value_type = fields.Selection([
        ('string', 'Text'),
        ('integer', 'Number'),
        ('boolean', 'Yes/No'),
    ], string="Value Type", default='string')
    string_value = fields.Char(string='Text Value')
    integer_value = fields.Integer(string='Number Value')
    boolean_value = fields.Boolean(string='Yes/No Value')
    
    @api.model
    def default_get(self, fields_list):
        """Load current values from the CI relation."""
        res = super().default_get(fields_list)
        
        if 'ci_relation_id' in res and res['ci_relation_id']:
            relation = self.env['myschool.ci.relation'].browse(res['ci_relation_id'])
            if relation.exists() and relation.id_ci:
                ci = relation.id_ci
                res['ci_name'] = ci.name
                res['org_name'] = relation.id_org.name if relation.id_org else ''
                
                # Determine value type and load value
                if ci.string_value:
                    res['value_type'] = 'string'
                    res['string_value'] = ci.string_value
                elif ci.integer_value:
                    res['value_type'] = 'integer'
                    res['integer_value'] = ci.integer_value
                elif ci.boolean_value is not None:
                    res['value_type'] = 'boolean'
                    res['boolean_value'] = ci.boolean_value
        
        return res
    
    def action_save(self):
        """Save the updated value."""
        self.ensure_one()
        
        if not self.ci_relation_id or not self.ci_relation_id.id_ci:
            raise UserError("Invalid Configuration Item relation")
        
        ci = self.ci_relation_id.id_ci
        
        # Update value based on type
        vals = {
            'string_value': False,
            'integer_value': 0,
            'boolean_value': False,
        }
        
        if self.value_type == 'string':
            vals['string_value'] = self.string_value
        elif self.value_type == 'integer':
            vals['integer_value'] = self.integer_value
        elif self.value_type == 'boolean':
            vals['boolean_value'] = self.boolean_value
        
        ci.write(vals)
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class RemoveCiRelationWizard(models.TransientModel):
    """Wizard to remove (deactivate) a Configuration Item relation."""
    _name = 'myschool.remove.ci.relation.wizard'
    _description = 'Remove Configuration Item'

    ci_relation_id = fields.Many2one('myschool.ci.relation', string='Relation', required=True)
    ci_name = fields.Char(string='Config Item', readonly=True)
    org_name = fields.Char(string='Organization', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        """Load info from the CI relation."""
        res = super().default_get(fields_list)
        
        if 'ci_relation_id' in res and res['ci_relation_id']:
            relation = self.env['myschool.ci.relation'].browse(res['ci_relation_id'])
            if relation.exists():
                res['ci_name'] = relation.id_ci.name if relation.id_ci else ''
                res['org_name'] = relation.id_org.name if relation.id_org else ''
        
        return res
    
    def action_remove(self):
        """Deactivate the CI relation."""
        self.ensure_one()
        
        if self.ci_relation_id:
            self.ci_relation_id.write({'isactive': False})
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}


# =============================================================================
# Role Relations Manager
# =============================================================================

class RoleRelationsManager(models.TransientModel):
    """
    Manager for Role-based PropRelations.
    
    Manages three types of relations:
    1. SRBR: SAP-Role to Backend-Role mapping
    2. BRSO: Backend-Role to School+Department mapping (determines where persons are created)
    3. PPBRSO: Like BRSO but also includes Person and Period
    """
    _name = 'myschool.role.relations.manager'
    _description = 'Role Relations Manager'

    relation_type = fields.Selection([
        ('SRBR', 'SAP-Role to Backend-Role (SRBR)'),
        ('BRSO', 'Backend-Role to School/Department (BRSO)'),
        ('PPBRSO', 'Person/Period Backend-Role to School/Department (PPBRSO)'),
    ], string='Relation Type', default='SRBR', required=True)
    
    # Computed counts
    srbr_count = fields.Integer(compute='_compute_counts', string='SRBR Relations')
    brso_count = fields.Integer(compute='_compute_counts', string='BRSO Relations')
    ppbrso_count = fields.Integer(compute='_compute_counts', string='PPBRSO Relations')
    
    @api.depends('relation_type')
    def _compute_counts(self):
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        for wizard in self:
            # Count SRBR relations
            srbr_type = PropRelationType.search([('name', '=', 'SRBR')], limit=1)
            wizard.srbr_count = PropRelation.search_count([
                ('proprelation_type_id', '=', srbr_type.id),
                ('is_active', '=', True)
            ]) if srbr_type else 0
            
            # Count BRSO relations
            brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
            wizard.brso_count = PropRelation.search_count([
                ('proprelation_type_id', '=', brso_type.id),
                ('is_active', '=', True)
            ]) if brso_type else 0
            
            # Count PPBRSO relations
            ppbrso_type = PropRelationType.search([('name', '=', 'PPBRSO')], limit=1)
            wizard.ppbrso_count = PropRelation.search_count([
                ('proprelation_type_id', '=', ppbrso_type.id),
                ('is_active', '=', True)
            ]) if ppbrso_type else 0
    
    def action_view_srbr(self):
        """View all SRBR relations."""
        return self._view_relations('SRBR')
    
    def action_view_brso(self):
        """View all BRSO relations."""
        return self._view_relations('BRSO')
    
    def action_view_ppbrso(self):
        """View all PPBRSO relations."""
        return self._view_relations('PPBRSO')
    
    def _view_relations(self, type_name):
        """View relations of a specific type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
        
        domain = [('is_active', '=', True)]
        if rel_type:
            domain.append(('proprelation_type_id', '=', rel_type.id))
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'{type_name} Relations',
            'res_model': 'myschool.proprelation',
            'view_mode': 'tree,form',
            'domain': domain,
            'target': 'current',
        }
    
    def action_add_srbr(self):
        """Open wizard to add SRBR relation."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.srbr.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }
    
    def action_add_brso(self):
        """Open wizard to add BRSO relation."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.brso.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }
    
    def action_add_ppbrso(self):
        """Open wizard to add PPBRSO relation."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.ppbrso.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }


class AddSRBRWizard(models.TransientModel):
    """
    Wizard to create SRBR relation.
    Links a SAP-Role to a Backend-Role.
    Uses role_type_id to filter by role type (BACKEND, SAP).
    """
    _name = 'myschool.add.srbr.wizard'
    _description = 'Add SAP-Role to Backend-Role Relation'

    sap_role_id = fields.Many2one(
        'myschool.role', 
        string='SAP Role',
        required=True,
        domain="[('role_type_id.name', '=', 'SAP')]",
        help='Select the SAP role'
    )
    backend_role_id = fields.Many2one(
        'myschool.role', 
        string='Backend Role',
        required=True,
        domain="[('role_type_id.name', '=', 'BACKEND')]",
        help='Select the backend role to link to'
    )
    
    def _get_or_create_relation_type(self, name, usage=''):
        """Get or create a proprelation type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', name)], limit=1)
        if not rel_type:
            rel_type = PropRelationType.create({
                'name': name,
                'usage': usage,
                'is_active': True,
            })
        return rel_type
    
    def action_add(self):
        """Create the SRBR relation."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create SRBR type
        rel_type = self._get_or_create_relation_type(
            'SRBR', 
            'SAP-Role to Backend-Role mapping'
        )
        
        # Check if relation already exists
        existing = PropRelation.search([
            ('proprelation_type_id', '=', rel_type.id),
            ('id_role', '=', self.sap_role_id.id),
            ('id_role_parent', '=', self.backend_role_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError('This relation already exists.')
        
        # Build relation name: SRBR.Ro={sap_role}.RoP={backend_role}
        sap_name = self.sap_role_id.shortname or self.sap_role_id.name
        backend_name = self.backend_role_id.shortname or self.backend_role_id.name
        rel_name = f"SRBR.Ro={sap_name}.RoP={backend_name}"
        
        # Create the relation
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': rel_type.id,
            'id_role': self.sap_role_id.id,
            'id_role_parent': self.backend_role_id.id,
            'is_active': True,
        })
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_add_and_new(self):
        """Create and open new wizard."""
        self.action_add()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.srbr.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }


class AddBRSOWizard(models.TransientModel):
    """
    Wizard to create BRSO relation.
    Links a Backend-Role to a School and Department.
    Used to determine where persons with a certain role in a school will be created.
    
    Field mapping:
    - id_role = Backend Role
    - id_org = Department (where person will be created)
    - id_org_parent = School (higher level in tree)
    """
    _name = 'myschool.add.brso.wizard'
    _description = 'Add Backend-Role to School/Department Relation'

    backend_role_id = fields.Many2one(
        'myschool.role', 
        string='Backend Role',
        required=True,
        domain="[('role_type_id.name', '=', 'BACKEND')]",
        help='Select the backend role'
    )
    school_id = fields.Many2one(
        'myschool.org', 
        string='School',
        required=True,
        domain="[('org_type_id.name', '=', 'SCHOOL')]",
        help='Select the school (org with type SCHOOL)'
    )
    department_id = fields.Many2one(
        'myschool.org', 
        string='Department',
        required=True,
        domain="[('org_type_id.name', '=', 'DEPARTMENT')]",
        help='Select the department where persons will be created'
    )
    
    def _get_or_create_relation_type(self, name, usage=''):
        """Get or create a proprelation type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', name)], limit=1)
        if not rel_type:
            rel_type = PropRelationType.create({
                'name': name,
                'usage': usage,
                'is_active': True,
            })
        return rel_type
    
    def action_add(self):
        """Create the BRSO relation."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create BRSO type
        rel_type = self._get_or_create_relation_type(
            'BRSO', 
            'Backend-Role to School/Department mapping for person creation'
        )
        
        # Check if relation already exists
        # id_org = department, id_org_parent = school
        existing = PropRelation.search([
            ('proprelation_type_id', '=', rel_type.id),
            ('id_role', '=', self.backend_role_id.id),
            ('id_org', '=', self.department_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError('This relation already exists.')
        
        # Build relation name: BRSO.Ro={role}.OrP={school}.Or={dept}
        role_name = self.backend_role_id.shortname or self.backend_role_id.name
        school_name = self.school_id.name_short if hasattr(self.school_id, 'name_short') and self.school_id.name_short else self.school_id.name
        dept_name = self.department_id.name_short if hasattr(self.department_id, 'name_short') and self.department_id.name_short else self.department_id.name
        rel_name = f"BRSO.Ro={role_name}.OrP={school_name}.Or={dept_name}"
        
        # Create the relation
        # id_org = department (where person created), id_org_parent = school (higher level)
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': rel_type.id,
            'id_role': self.backend_role_id.id,
            'id_org': self.department_id.id,
            'id_org_parent': self.school_id.id,
            'is_active': True,
        })
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_add_and_new(self):
        """Create and open new wizard."""
        self.action_add()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.brso.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }


class AddPPBRSOWizard(models.TransientModel):
    """
    Wizard to create PPBRSO relation.
    Like BRSO but also links a Person and Period.
    
    Field mapping:
    - id_person = Person
    - id_period = Period
    - id_role = Backend Role
    - id_org = Department (where person will be created)
    - id_org_parent = School (higher level in tree)
    """
    _name = 'myschool.add.ppbrso.wizard'
    _description = 'Add Person/Period Backend-Role to School/Department Relation'

    person_id = fields.Many2one(
        'myschool.person', 
        string='Person',
        required=True,
        help='Select the person'
    )
    period_id = fields.Many2one(
        'myschool.period', 
        string='Period',
        required=True,
        help='Select the period'
    )
    backend_role_id = fields.Many2one(
        'myschool.role', 
        string='Backend Role',
        required=True,
        domain="[('role_type_id.name', '=', 'BACKEND')]",
        help='Select the backend role'
    )
    school_id = fields.Many2one(
        'myschool.org', 
        string='School',
        required=True,
        domain="[('org_type_id.name', '=', 'SCHOOL')]",
        help='Select the school (org with type SCHOOL)'
    )
    department_id = fields.Many2one(
        'myschool.org', 
        string='Department',
        required=True,
        domain="[('org_type_id.name', '=', 'DEPARTMENT')]",
        help='Select the department where the person will be created'
    )
    
    def _get_or_create_relation_type(self, name, usage=''):
        """Get or create a proprelation type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', name)], limit=1)
        if not rel_type:
            rel_type = PropRelationType.create({
                'name': name,
                'usage': usage,
                'is_active': True,
            })
        return rel_type
    
    def action_add(self):
        """Create the PPBRSO relation."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create PPBRSO type
        rel_type = self._get_or_create_relation_type(
            'PPBRSO', 
            'Person/Period Backend-Role to School/Department mapping'
        )
        
        # Check if relation already exists
        # id_org = department, id_org_parent = school
        existing = PropRelation.search([
            ('proprelation_type_id', '=', rel_type.id),
            ('id_person', '=', self.person_id.id),
            ('id_period', '=', self.period_id.id),
            ('id_role', '=', self.backend_role_id.id),
            ('id_org', '=', self.department_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError('This relation already exists.')
        
        # Build relation name: PPBRSO.Pn={person}.Pd={period}.Ro={role}.Or={dept}.OrP={school}
        person_name = self.person_id.name
        if hasattr(self.person_id, 'first_name') and self.person_id.first_name:
            person_name = f"{self.person_id.first_name} {person_name}"
        period_name = self.period_id.name
        role_name = self.backend_role_id.shortname or self.backend_role_id.name
        school_name = self.school_id.name_short if hasattr(self.school_id, 'name_short') and self.school_id.name_short else self.school_id.name
        dept_name = self.department_id.name_short if hasattr(self.department_id, 'name_short') and self.department_id.name_short else self.department_id.name
        rel_name = f"PPBRSO.Pn={person_name}.Pd={period_name}.Ro={role_name}.Or={dept_name}.OrP={school_name}"
        
        # Create the relation
        # id_org = department, id_org_parent = school (higher level)
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': rel_type.id,
            'id_person': self.person_id.id,
            'id_period': self.period_id.id,
            'id_role': self.backend_role_id.id,
            'id_org': self.department_id.id,
            'id_org_parent': self.school_id.id,
            'is_active': True,
        })
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_add_and_new(self):
        """Create and open new wizard."""
        self.action_add()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.ppbrso.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }


class LinkRoleToOrgWizard(models.TransientModel):
    """
    Wizard to link a Role to an Organization (BRSO relation).
    Opens from the Organization context menu.
    
    Creates a BRSO relation where:
    - id_org = the selected org (as department)
    - id_org_parent = the school (auto-detected from hierarchy)
    - id_role = selected backend role
    """
    _name = 'myschool.link.role.org.wizard'
    _description = 'Link Role to Organization'

    org_id = fields.Many2one(
        'myschool.org', 
        string='Organization',
        required=True,
        readonly=True,
        help='The organization to link the role to'
    )
    org_name = fields.Char(string='Organization', compute='_compute_org_info')
    org_type_name = fields.Char(string='Organization Type', compute='_compute_org_info')
    
    school_id = fields.Many2one(
        'myschool.org', 
        string='School',
        domain="[('org_type_id.name', '=', 'SCHOOL')]",
        help='Select the school (auto-detected if possible)'
    )
    
    backend_role_id = fields.Many2one(
        'myschool.role', 
        string='Backend Role',
        required=True,
        domain="[('role_type_id.name', '=', 'BACKEND')]",
        help='Select the backend role to link'
    )
    
    @api.depends('org_id')
    def _compute_org_info(self):
        for wizard in self:
            if wizard.org_id:
                wizard.org_name = wizard.org_id.name
                wizard.org_type_name = wizard.org_id.org_type_id.name if wizard.org_id.org_type_id else ''
            else:
                wizard.org_name = ''
                wizard.org_type_name = ''
    
    @api.model
    def default_get(self, fields_list):
        """Set defaults and auto-detect school from hierarchy."""
        res = super().default_get(fields_list)
        
        if 'org_id' in res and res['org_id']:
            org = self.env['myschool.org'].browse(res['org_id'])
            if org.exists():
                # Try to find the school in the hierarchy
                school = self._find_school_in_hierarchy(org)
                if school:
                    res['school_id'] = school.id
        
        return res
    
    def _find_school_in_hierarchy(self, org):
        """Find the school in the organization hierarchy."""
        PropRelation = self.env.get('myschool.proprelation')
        if not PropRelation:
            return None
        
        # Check if current org is a school
        if org.org_type_id and org.org_type_id.name == 'SCHOOL':
            return org
        
        # Walk up the hierarchy to find a school
        current_org = org
        visited = set()
        
        while current_org and current_org.id not in visited:
            visited.add(current_org.id)
            
            # Check if this org is a school
            if current_org.org_type_id and current_org.org_type_id.name == 'SCHOOL':
                return current_org
            
            # Find parent
            parent_rel = PropRelation.search([
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
            if parent_rel and parent_rel.id_org_parent:
                current_org = parent_rel.id_org_parent
            else:
                break
        
        return None
    
    def _get_or_create_relation_type(self, name, usage=''):
        """Get or create a proprelation type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', name)], limit=1)
        if not rel_type:
            rel_type = PropRelationType.create({
                'name': name,
                'usage': usage,
                'is_active': True,
            })
        return rel_type
    
    def action_link(self):
        """Create the BRSO relation."""
        self.ensure_one()
        
        if not self.school_id:
            raise UserError('Please select a school.')
        
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create BRSO type
        rel_type = self._get_or_create_relation_type(
            'BRSO', 
            'Backend-Role to School/Department mapping for person creation'
        )
        
        # Check if relation already exists
        existing = PropRelation.search([
            ('proprelation_type_id', '=', rel_type.id),
            ('id_role', '=', self.backend_role_id.id),
            ('id_org', '=', self.org_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError('This relation already exists.')
        
        # Build relation name: BRSO.Ro={role}.OrP={school}.Or={dept}
        role_name = self.backend_role_id.shortname or self.backend_role_id.name
        school_name = self.school_id.name_short if hasattr(self.school_id, 'name_short') and self.school_id.name_short else self.school_id.name
        org_name = self.org_id.name_short if hasattr(self.org_id, 'name_short') and self.org_id.name_short else self.org_id.name
        rel_name = f"BRSO.Ro={role_name}.OrP={school_name}.Or={org_name}"
        
        # Create the relation
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': rel_type.id,
            'id_role': self.backend_role_id.id,
            'id_org': self.org_id.id,
            'id_org_parent': self.school_id.id,
            'is_active': True,
        })
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_link_and_new(self):
        """Create and open new wizard for same org."""
        self.action_link()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.link.role.org.wizard',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_org_id': self.org_id.id,
            },
        }
