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
    
    # Person fields
    first_name = fields.Char(string='First Name', required=True)
    last_name = fields.Char(string='Last Name', required=True)
    email = fields.Char(string='Email')
    
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

    @api.onchange('email')
    def _onchange_email(self):
        """Default login to email."""
        if self.email and not self.odoo_user_login:
            self.odoo_user_login = self.email

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
        
        if self.email and 'email' in Person._fields:
            person_vals['email'] = self.email
        
        # Handle Odoo user linking/creation
        user = None
        if self.link_existing_user and self.existing_user_id:
            user = self.existing_user_id
        elif self.create_odoo_user:
            # Create new Odoo user
            login = self.odoo_user_login or self.email
            if not login:
                raise UserError("Login or email is required to create Odoo user")
            
            # Check if login already exists
            existing_user = self.env['res.users'].search([('login', '=', login)], limit=1)
            if existing_user:
                raise UserError(f"A user with login '{login}' already exists")
            
            user = self.env['res.users'].create({
                'name': f"{self.first_name} {self.last_name}",
                'login': login,
                'email': self.email or login,
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
        
        if self.email and 'email' in Person._fields:
            person_vals['email'] = self.email
        
        # Handle Odoo user
        user = None
        if self.link_existing_user and self.existing_user_id:
            user = self.existing_user_id
        elif self.create_odoo_user:
            login = self.odoo_user_login or self.email
            if not login:
                raise UserError("Login or email is required to create Odoo user")
            
            existing_user = self.env['res.users'].search([('login', '=', login)], limit=1)
            if existing_user:
                raise UserError(f"A user with login '{login}' already exists")
            
            user = self.env['res.users'].create({
                'name': f"{self.first_name} {self.last_name}",
                'login': login,
                'email': self.email or login,
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
    
    # LDAP OU fields - inherited from parent with prepended name_short
    new_org_ou_fqdn_intern = fields.Char(string='OU FQDN Intern',
        help='Internal LDAP OU path (auto-generated from parent)',
        compute='_compute_inherited_fields', store=True, readonly=False, precompute=True)
    new_org_ou_fqdn_extern = fields.Char(string='OU FQDN Extern',
        help='External LDAP OU path (auto-generated from parent)',
        compute='_compute_inherited_fields', store=True, readonly=False, precompute=True)
    
    # Boolean flags
    new_org_has_ou = fields.Boolean(string='Heeft OU', default=False)
    new_org_has_role = fields.Boolean(string='Heeft Role', default=False)
    new_org_has_comgroup = fields.Boolean(string='Heeft Communicatiegroep', default=False)
    new_org_has_secgroup = fields.Boolean(string='Heeft Securitygroep', default=False)
    
    # Optional fields
    new_org_type_id = fields.Many2one('myschool.org.type', string='Organization Type')
    new_org_description = fields.Text(string='Description')

    @api.depends('parent_org_id', 'new_org_name_short')
    def _compute_inherited_fields(self):
        """Auto-inherit fields from parent organization."""
        for wizard in self:
            if wizard.parent_org_id:
                parent = wizard.parent_org_id
                
                # Inherit inst_nr
                if hasattr(parent, 'inst_nr') and parent.inst_nr:
                    wizard.new_org_inst_nr = parent.inst_nr
                else:
                    wizard.new_org_inst_nr = False
                
                # Build OU FQDN paths with prepended name_short
                short_name = wizard.new_org_name_short or 'NEW'
                ou_prefix = f"ou={short_name},"
                
                # OU FQDN Internal
                if hasattr(parent, 'ou_fqdn_internal') and parent.ou_fqdn_internal:
                    wizard.new_org_ou_fqdn_intern = ou_prefix + parent.ou_fqdn_internal
                else:
                    wizard.new_org_ou_fqdn_intern = False
                
                # OU FQDN External
                if hasattr(parent, 'ou_fqdn_external') and parent.ou_fqdn_external:
                    wizard.new_org_ou_fqdn_extern = ou_prefix + parent.ou_fqdn_external
                else:
                    wizard.new_org_ou_fqdn_extern = False
            else:
                wizard.new_org_inst_nr = False
                wizard.new_org_ou_fqdn_intern = False
                wizard.new_org_ou_fqdn_extern = False

    @api.onchange('new_org_name_short')
    def _onchange_name_short_update_fqdn(self):
        """Update OU FQDN when short name changes."""
        if self.parent_org_id and self.new_org_name_short:
            parent = self.parent_org_id
            ou_prefix = f"ou={self.new_org_name_short},"
            
            # OU FQDN Internal
            if hasattr(parent, 'ou_fqdn_internal') and parent.ou_fqdn_internal:
                self.new_org_ou_fqdn_intern = ou_prefix + parent.ou_fqdn_internal
            
            # OU FQDN External
            if hasattr(parent, 'ou_fqdn_external') and parent.ou_fqdn_external:
                self.new_org_ou_fqdn_extern = ou_prefix + parent.ou_fqdn_external

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
        
        # Create new parent relation
        PropRelation.create({
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
        
        PropRelation.create({
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
