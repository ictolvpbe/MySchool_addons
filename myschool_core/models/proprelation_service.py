# -*- coding: utf-8 -*-
"""
PropRelation Service for Odoo 19
================================

Generic service for creating, updating, and managing PropRelation records.
Provides standardized name generation and field mapping.

Usage:
    proprel_service = self.env['myschool.proprelation.service']
    
    # Create using field names
    proprel = proprel_service.create_proprelation(
        type_name='PPSBR',
        person=person_record,
        role=role_record,
        org=org_record,
        period=period_record
    )
    
    # Create using parameter dict
    proprel = proprel_service.create_proprelation_from_dict(
        type_name='BRSO',
        params={
            'role': role_record,
            'org': org_record,
        }
    )
    
    # Update existing
    proprel_service.update_proprelation(proprel, role=new_role)
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Optional, Dict, Any, Union
import logging

_logger = logging.getLogger(__name__)


# =============================================================================
# STANDALONE HELPER FUNCTION - Can be imported elsewhere
# =============================================================================

def build_proprelation_name(proprelation_type_name: str, **kwargs) -> str:
    """
    Build a standardized proprelation name.
    
    Format: TYPE:Abbr1=value1,Abbr2=value2,...
    Example: BRSO:Ro=EMPLOYEE,OrP=int.olvp.bawa,Or=int.olvp.bawa.pers.lkr
    
    Field abbreviations:
        id_org -> Or (uses name_tree or name)
        id_org_parent -> OrP (uses name_tree or name)
        id_org_child -> OrC (uses name_tree or name)
        id_period -> Pd (uses name)
        id_period_parent -> PdP (uses name)
        id_period_child -> PdC (uses name)
        id_role -> Ro (uses name)
        id_role_parent -> RoP (uses name)
        id_role_child -> RoC (uses name)
        id_person -> Pn (uses name)
        id_person_parent -> PnP (uses name)
        id_person_child -> PnC (uses name)
    
    Args:
        proprelation_type_name: The type name (e.g., 'BRSO', 'ORG-TREE', 'PERSON-TREE')
        **kwargs: Field values as records or dicts with name/name_tree
    
    Returns:
        String like 'BRSO:Ro=EMPLOYEE,OrP=int.olvp.bawa'
    """
    # Field mapping: field_name -> (abbreviation, primary_field, fallback_field)
    field_map = {
        'id_org': ('Or', 'name_tree', 'name'),
        'id_org_parent': ('OrP', 'name_tree', 'name'),
        'id_org_child': ('OrC', 'name_tree', 'name'),
        'id_period': ('Pd', 'name', 'name'),
        'id_period_parent': ('PdP', 'name', 'name'),
        'id_period_child': ('PdC', 'name', 'name'),
        'id_role': ('Ro', 'name', 'name'),
        'id_role_parent': ('RoP', 'name', 'name'),
        'id_role_child': ('RoC', 'name', 'name'),
        'id_person': ('Pn', 'name', 'name'),
        'id_person_parent': ('PnP', 'name', 'name'),
        'id_person_child': ('PnC', 'name', 'name'),
    }
    
    # Order of fields in the name (for consistent output)
    field_order = [
        'id_role', 'id_role_parent', 'id_role_child',
        'id_org_parent', 'id_org', 'id_org_child',
        'id_person', 'id_person_parent', 'id_person_child',
        'id_period', 'id_period_parent', 'id_period_child',
    ]
    
    parts = []
    
    for field_name in field_order:
        if field_name in kwargs and kwargs[field_name]:
            record = kwargs[field_name]
            abbr, primary_field, fallback_field = field_map[field_name]
            
            # Get value from record (handle both Odoo records and dicts)
            value = None
            if isinstance(record, dict):
                value = record.get(primary_field) or record.get(fallback_field) or record.get('name')
            else:
                if hasattr(record, primary_field) and getattr(record, primary_field):
                    value = getattr(record, primary_field)
                elif hasattr(record, fallback_field) and getattr(record, fallback_field):
                    value = getattr(record, fallback_field)
                elif hasattr(record, 'name'):
                    value = record.name
            
            if value:
                parts.append(f"{abbr}={value}")
    
    # Build the full name
    type_prefix = proprelation_type_name.upper() if proprelation_type_name else 'UNKNOWN'
    
    if parts:
        return f"{type_prefix}:{','.join(parts)}"
    return type_prefix


# =============================================================================
# PARAMETER NAME MAPPING
# =============================================================================

# Maps friendly parameter names to PropRelation field names
PARAM_TO_FIELD_MAP = {
    # Org mappings
    'org': 'id_org',
    'organization': 'id_org',
    'id_org': 'id_org',
    'org_parent': 'id_org_parent',
    'organization_parent': 'id_org_parent',
    'parent_org': 'id_org_parent',
    'id_org_parent': 'id_org_parent',
    'org_child': 'id_org_child',
    'organization_child': 'id_org_child',
    'child_org': 'id_org_child',
    'id_org_child': 'id_org_child',
    
    # Role mappings
    'role': 'id_role',
    'id_role': 'id_role',
    'role_parent': 'id_role_parent',
    'parent_role': 'id_role_parent',
    'id_role_parent': 'id_role_parent',
    'role_child': 'id_role_child',
    'child_role': 'id_role_child',
    'id_role_child': 'id_role_child',
    
    # Person mappings
    'person': 'id_person',
    'id_person': 'id_person',
    'person_parent': 'id_person_parent',
    'parent_person': 'id_person_parent',
    'id_person_parent': 'id_person_parent',
    'person_child': 'id_person_child',
    'child_person': 'id_person_child',
    'id_person_child': 'id_person_child',
    
    # Period mappings
    'period': 'id_period',
    'id_period': 'id_period',
    'period_parent': 'id_period_parent',
    'parent_period': 'id_period_parent',
    'id_period_parent': 'id_period_parent',
    'period_child': 'id_period_child',
    'child_period': 'id_period_child',
    'id_period_child': 'id_period_child',
    
    # Other fields
    'priority': 'priority',
    'is_active': 'is_active',
    'active': 'is_active',
}


class PropRelationService(models.AbstractModel):
    """
    Service for managing PropRelation records.
    
    Provides:
    - Standardized name generation
    - Parameter name translation (friendly names -> field names)
    - Create, update, deactivate, find operations
    - Type-specific helpers
    """
    _name = 'myschool.proprelation.service'
    _description = 'PropRelation Service'

    # =========================================================================
    # PARAMETER TRANSLATION
    # =========================================================================
    
    def _translate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate friendly parameter names to PropRelation field names.
        
        @param params: Dict with friendly names (e.g., {'person': record, 'role': record})
        @return: Dict with field names (e.g., {'id_person': record, 'id_role': record})
        """
        translated = {}
        
        for key, value in params.items():
            if key in PARAM_TO_FIELD_MAP:
                field_name = PARAM_TO_FIELD_MAP[key]
                translated[field_name] = value
            else:
                # Pass through unknown keys
                translated[key] = value
        
        return translated
    
    def _extract_record_id(self, value: Any) -> Optional[int]:
        """
        Extract record ID from various input types.
        
        @param value: Can be int, record, or dict with 'id'
        @return: Integer ID or None
        """
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, dict):
            return value.get('id')
        if hasattr(value, 'id'):
            return value.id
        return None

    # =========================================================================
    # NAME GENERATION
    # =========================================================================
    
    def build_name(self, type_name: str, **kwargs) -> str:
        """
        Build standardized PropRelation name.
        
        @param type_name: PropRelation type name (e.g., 'PPSBR', 'BRSO')
        @param kwargs: Field values (can use friendly names or field names)
        @return: Standardized name string
        """
        # Translate friendly names to field names
        translated = self._translate_params(kwargs)
        return build_proprelation_name(type_name, **translated)
    
    def compute_name_for_record(self, proprel) -> Optional[str]:
        """
        Compute the standardized name for an existing PropRelation record.
        
        @param proprel: PropRelation record
        @return: Standardized name or None
        """
        if not proprel or not proprel.proprelation_type_id:
            return None
        
        type_name = proprel.proprelation_type_id.name
        
        kwargs = {}
        field_names = [
            'id_org', 'id_org_parent', 'id_org_child',
            'id_role', 'id_role_parent', 'id_role_child',
            'id_person', 'id_person_parent', 'id_person_child',
            'id_period', 'id_period_parent', 'id_period_child',
        ]
        
        for field_name in field_names:
            if hasattr(proprel, field_name):
                value = getattr(proprel, field_name)
                if value:
                    kwargs[field_name] = value
        
        if kwargs:
            return build_proprelation_name(type_name, **kwargs)
        return type_name

    # =========================================================================
    # TYPE MANAGEMENT
    # =========================================================================
    
    def get_or_create_type(self, type_name: str, usage: str = None) -> 'PropRelationType':
        """
        Get or create a PropRelationType by name.
        
        @param type_name: Type name (e.g., 'PPSBR', 'BRSO', 'PERSON-TREE')
        @param usage: Optional usage description
        @return: PropRelationType record
        """
        PropRelationType = self.env['myschool.proprelation.type']
        
        rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
        
        if not rel_type:
            vals = {
                'name': type_name,
                'is_active': True,
            }
            if usage:
                vals['usage'] = usage
            rel_type = PropRelationType.create(vals)
            _logger.info(f'Created PropRelationType: {type_name}')
        
        return rel_type

    # =========================================================================
    # CREATE OPERATIONS
    # =========================================================================
    
    def create_proprelation(
        self,
        type_name: str,
        auto_name: bool = True,
        **kwargs
    ) -> 'PropRelation':
        """
        Create a new PropRelation with standardized name.
        
        @param type_name: PropRelation type name (e.g., 'PPSBR', 'BRSO')
        @param auto_name: If True, generate standardized name automatically
        @param kwargs: Field values using friendly names:
            - person, person_parent, person_child
            - org, org_parent, org_child  
            - role, role_parent, role_child
            - period, period_parent, period_child
            - priority, is_active
        @return: Created PropRelation record
        
        Example:
            proprel = service.create_proprelation(
                'PPSBR',
                person=person_record,
                role=role_record,
                org=org_record,
                period=period_record,
                priority=10
            )
        """
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create the type
        rel_type = self.get_or_create_type(type_name)
        
        # Translate parameters to field names
        translated = self._translate_params(kwargs)
        
        # Build values dict
        vals = {
            'proprelation_type_id': rel_type.id,
            'is_active': True,
        }
        
        # Add translated fields, converting records to IDs
        name_kwargs = {}
        for field_name, value in translated.items():
            if field_name.startswith('id_'):
                # This is a relation field - extract ID for vals, keep record for name
                record_id = self._extract_record_id(value)
                if record_id:
                    vals[field_name] = record_id
                    name_kwargs[field_name] = value  # Keep record for name building
            elif field_name in ('priority', 'is_active'):
                vals[field_name] = value
        
        # Generate name if auto_name
        if auto_name:
            vals['name'] = build_proprelation_name(type_name, **name_kwargs)
        elif 'name' in kwargs:
            vals['name'] = kwargs['name']
        else:
            vals['name'] = type_name
        
        # Create the record
        proprel = PropRelation.create(vals)
        _logger.info(f'Created PropRelation: {proprel.name} (ID: {proprel.id})')
        
        return proprel
    
    def create_proprelation_from_dict(
        self,
        type_name: str,
        params: Dict[str, Any],
        auto_name: bool = True
    ) -> 'PropRelation':
        """
        Create PropRelation from a dictionary of parameters.
        
        @param type_name: PropRelation type name
        @param params: Dict with field values (friendly names allowed)
        @param auto_name: Generate standardized name automatically
        @return: Created PropRelation record
        
        Example:
            proprel = service.create_proprelation_from_dict(
                'BRSO',
                {'role': role_record, 'org': org_record}
            )
        """
        return self.create_proprelation(type_name, auto_name=auto_name, **params)

    # =========================================================================
    # UPDATE OPERATIONS
    # =========================================================================
    
    def update_proprelation(
        self,
        proprel,
        update_name: bool = True,
        **kwargs
    ) -> bool:
        """
        Update an existing PropRelation.
        
        @param proprel: PropRelation record to update
        @param update_name: If True, regenerate the standardized name
        @param kwargs: Fields to update (friendly names allowed)
        @return: True if updated
        
        Example:
            service.update_proprelation(proprel, role=new_role, priority=20)
        """
        if not proprel or not proprel.exists():
            _logger.warning('Cannot update: PropRelation does not exist')
            return False
        
        # Translate parameters
        translated = self._translate_params(kwargs)
        
        # Build update values
        vals = {}
        for field_name, value in translated.items():
            if field_name.startswith('id_'):
                record_id = self._extract_record_id(value)
                if record_id is not None:
                    vals[field_name] = record_id
            elif field_name in ('priority', 'is_active'):
                vals[field_name] = value
        
        # Update the record
        if vals:
            proprel.write(vals)
        
        # Regenerate name if requested
        if update_name:
            new_name = self.compute_name_for_record(proprel)
            if new_name and proprel.name != new_name:
                proprel.write({'name': new_name})
        
        _logger.info(f'Updated PropRelation: {proprel.name} (ID: {proprel.id})')
        return True
    
    def update_proprelation_name(self, proprel) -> bool:
        """
        Update only the name of a PropRelation to the standardized format.
        
        @param proprel: PropRelation record
        @return: True if name was updated
        """
        if not proprel or not proprel.exists():
            return False
        
        new_name = self.compute_name_for_record(proprel)
        if new_name and proprel.name != new_name:
            proprel.write({'name': new_name})
            _logger.debug(f'Updated name: {new_name}')
            return True
        return False

    # =========================================================================
    # FIND OPERATIONS
    # =========================================================================
    
    def find_proprelation(
        self,
        type_name: str,
        active_only: bool = True,
        **kwargs
    ) -> Optional['PropRelation']:
        """
        Find a PropRelation by type and field values.
        
        @param type_name: PropRelation type name
        @param active_only: If True, only search active records
        @param kwargs: Field values to match (friendly names allowed)
        @return: PropRelation record or None
        
        Example:
            proprel = service.find_proprelation(
                'PPSBR',
                person=person_record,
                role=role_record,
                org=org_record
            )
        """
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        # Get the type
        rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
        if not rel_type:
            return None
        
        # Build domain
        domain = [('proprelation_type_id', '=', rel_type.id)]
        
        if active_only:
            domain.append(('is_active', '=', True))
        
        # Translate and add field conditions
        translated = self._translate_params(kwargs)
        for field_name, value in translated.items():
            if field_name.startswith('id_'):
                record_id = self._extract_record_id(value)
                if record_id:
                    domain.append((field_name, '=', record_id))
        
        return PropRelation.search(domain, limit=1) or None
    
    def find_all_proprelations(
        self,
        type_name: str = None,
        active_only: bool = True,
        **kwargs
    ) -> 'PropRelation':
        """
        Find all PropRelations matching criteria.
        
        @param type_name: Optional PropRelation type name filter
        @param active_only: If True, only search active records
        @param kwargs: Field values to match (friendly names allowed)
        @return: PropRelation recordset
        """
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        domain = []
        
        # Type filter
        if type_name:
            rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
            if rel_type:
                domain.append(('proprelation_type_id', '=', rel_type.id))
            else:
                return PropRelation.browse()  # Empty recordset
        
        if active_only:
            domain.append(('is_active', '=', True))
        
        # Translate and add field conditions
        translated = self._translate_params(kwargs)
        for field_name, value in translated.items():
            if field_name.startswith('id_'):
                record_id = self._extract_record_id(value)
                if record_id:
                    domain.append((field_name, '=', record_id))
        
        return PropRelation.search(domain)

    # =========================================================================
    # FIND OR CREATE
    # =========================================================================
    
    def find_or_create_proprelation(
        self,
        type_name: str,
        auto_name: bool = True,
        **kwargs
    ) -> tuple:
        """
        Find existing PropRelation or create new one.
        
        @param type_name: PropRelation type name
        @param auto_name: Generate standardized name if creating
        @param kwargs: Field values (friendly names allowed)
        @return: Tuple (PropRelation record, created: bool)
        
        Example:
            proprel, created = service.find_or_create_proprelation(
                'PPSBR',
                person=person_record,
                role=role_record
            )
        """
        # Try to find existing
        existing = self.find_proprelation(type_name, active_only=True, **kwargs)
        
        if existing:
            return existing, False
        
        # Check for inactive that can be reactivated
        inactive = self.find_proprelation(type_name, active_only=False, **kwargs)
        if inactive and not inactive.is_active:
            inactive.write({'is_active': True})
            if auto_name:
                self.update_proprelation_name(inactive)
            _logger.info(f'Reactivated PropRelation: {inactive.name} (ID: {inactive.id})')
            return inactive, False
        
        # Create new
        new_proprel = self.create_proprelation(type_name, auto_name=auto_name, **kwargs)
        return new_proprel, True

    # =========================================================================
    # DEACTIVATE OPERATIONS
    # =========================================================================
    
    def deactivate_proprelation(self, proprel) -> bool:
        """
        Deactivate (archive) a PropRelation.
        
        @param proprel: PropRelation record
        @return: True if deactivated
        """
        if not proprel or not proprel.exists():
            return False
        
        if proprel.is_active:
            proprel.write({'is_active': False})
            _logger.info(f'Deactivated PropRelation: {proprel.name} (ID: {proprel.id})')
        
        return True
    
    def deactivate_proprelations(
        self,
        type_name: str = None,
        **kwargs
    ) -> int:
        """
        Deactivate all PropRelations matching criteria.
        
        @param type_name: Optional type filter
        @param kwargs: Field values to match
        @return: Number of deactivated records
        """
        proprels = self.find_all_proprelations(type_name, active_only=True, **kwargs)
        
        count = 0
        for proprel in proprels:
            if self.deactivate_proprelation(proprel):
                count += 1
        
        return count

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================
    
    def update_all_names(self, type_name: str = None) -> Dict[str, int]:
        """
        Update names for all PropRelations (optionally filtered by type).
        
        @param type_name: Optional type filter
        @return: Dict with 'updated' and 'skipped' counts
        """
        PropRelation = self.env['myschool.proprelation']
        
        domain = [('proprelation_type_id', '!=', False)]
        
        if type_name:
            PropRelationType = self.env['myschool.proprelation.type']
            rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
            if rel_type:
                domain.append(('proprelation_type_id', '=', rel_type.id))
        
        all_proprels = PropRelation.search(domain)
        
        results = {'updated': 0, 'skipped': 0}
        
        for proprel in all_proprels:
            try:
                if self.update_proprelation_name(proprel):
                    results['updated'] += 1
                else:
                    results['skipped'] += 1
            except Exception as e:
                _logger.warning(f'Error updating name for PropRelation {proprel.id}: {e}')
                results['skipped'] += 1
        
        _logger.info(f"Updated {results['updated']} PropRelation names, skipped {results['skipped']}")
        return results

    # =========================================================================
    # TYPE-SPECIFIC HELPERS
    # =========================================================================
    
    def create_ppsbr(
        self,
        person,
        role,
        org=None,
        period=None,
        priority: int = 0
    ) -> 'PropRelation':
        """
        Create PPSBR (Person-Period-School-BackendRole) relation.
        
        @param person: Person record
        @param role: Role record
        @param org: Optional Org record
        @param period: Optional Period record
        @param priority: Priority value
        @return: Created PropRelation
        """
        return self.create_proprelation(
            'PPSBR',
            person=person,
            role=role,
            org=org,
            period=period,
            priority=priority
        )
    
    def create_brso(self, role, org) -> 'PropRelation':
        """
        Create BRSO (BackendRole-School-Org) relation.
        
        @param role: Role record
        @param org: Org record
        @return: Created PropRelation
        """
        return self.create_proprelation('BRSO', role=role, org=org)
    
    def create_sr_br(self, role_child, role_parent) -> 'PropRelation':
        """
        Create SR-BR (SapRole to BackendRole) mapping.
        
        @param role_child: SAP Role (child)
        @param role_parent: Backend Role (parent)
        @return: Created PropRelation
        """
        return self.create_proprelation(
            'SR-BR',
            role_child=role_child,
            role_parent=role_parent
        )
    
    def create_person_tree(self, person, org) -> 'PropRelation':
        """
        Create PERSON-TREE relation (person position in org tree).
        
        @param person: Person record
        @param org: Org record
        @return: Created PropRelation
        """
        return self.create_proprelation('PERSON-TREE', person=person, org=org)
    
    def create_org_tree(self, org, org_parent) -> 'PropRelation':
        """
        Create ORG-TREE relation (org hierarchy).
        
        @param org: Child Org record
        @param org_parent: Parent Org record
        @return: Created PropRelation
        """
        return self.create_proprelation('ORG-TREE', org=org, org_parent=org_parent)
