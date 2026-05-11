# -*- coding: utf-8 -*-
"""
Sync Model Registry
====================
Central registry defining which models are syncable, their natural keys,
syncable fields, Many2one reference mappings, and dependency priority.
"""

# Each entry: {
#   'model': Odoo model name,
#   'natural_key': list of field names forming the natural key,
#   'fields': list of field names to sync,
#   'references': dict mapping Many2one field -> {model, key_field},
#   'target_flag': field name on sync.target that controls sync for this model,
#   'priority': dependency ordering (lower = synced first),
#   'betask_object': object name for the API_*_SYNC betask type,
# }

SYNC_MODELS = [
    # --- Type models (priority 10) ---
    {
        'model': 'myschool.org.type',
        'natural_key': ['name'],
        'fields': ['name'],
        'references': {},
        'target_flag': 'sync_types',
        'priority': 10,
        'betask_object': 'CONFIG',
    },
    {
        'model': 'myschool.person.type',
        'natural_key': ['name'],
        'fields': ['name'],
        'references': {},
        'target_flag': 'sync_types',
        'priority': 10,
        'betask_object': 'CONFIG',
    },
    {
        'model': 'myschool.role.type',
        'natural_key': ['name'],
        'fields': ['name'],
        'references': {},
        'target_flag': 'sync_types',
        'priority': 10,
        'betask_object': 'CONFIG',
    },
    {
        'model': 'myschool.period.type',
        'natural_key': ['name'],
        'fields': ['name'],
        'references': {},
        'target_flag': 'sync_types',
        'priority': 10,
        'betask_object': 'CONFIG',
    },
    {
        'model': 'myschool.proprelation.type',
        'natural_key': ['name'],
        'fields': ['name', 'usage', 'is_active'],
        'references': {},
        'target_flag': 'sync_types',
        'priority': 10,
        'betask_object': 'CONFIG',
    },

    # --- Period (priority 20) ---
    {
        'model': 'myschool.period',
        'natural_key': ['name'],
        'fields': [
            'name', 'name_in_sap', 'start_date', 'end_date', 'is_active',
        ],
        'references': {
            'period_type_id': {'model': 'myschool.period.type', 'key_field': 'name'},
        },
        'target_flag': 'sync_period',
        'priority': 20,
        'betask_object': 'PERIOD',
    },

    # --- Org (priority 30) ---
    {
        'model': 'myschool.org',
        'natural_key': ['sync_uuid'],
        'fields': [
            'name', 'name_short', 'name_tree', 'inst_nr', 'is_active',
            'street', 'street_nr', 'postal_code', 'community', 'country',
            'is_administrative', 'domain_internal', 'domain_external',
            'has_ou', 'has_role', 'has_comgroup', 'has_secgroup', 'has_odoo_group',
            'ou_fqdn_internal', 'ou_fqdn_external',
            'com_group_fqdn_internal', 'com_group_fqdn_external',
            'sec_group_fqdn_internal', 'sec_group_fqdn_external',
            'com_group_name', 'com_group_email', 'sec_group_name',
        ],
        'references': {
            'org_type_id': {'model': 'myschool.org.type', 'key_field': 'name'},
        },
        'target_flag': 'sync_org',
        'priority': 30,
        'betask_object': 'ORG',
    },

    # --- Role (priority 30) ---
    {
        'model': 'myschool.role',
        'natural_key': ['shortname'],
        'fields': [
            'name', 'shortname', 'is_active', 'has_ui_access',
            'priority', 'description',
        ],
        'references': {
            'role_type_id': {'model': 'myschool.role.type', 'key_field': 'name'},
        },
        'target_flag': 'sync_role',
        'priority': 30,
        'betask_object': 'ROLE',
    },

    # --- Person (priority 40) ---
    {
        'model': 'myschool.person',
        'natural_key': ['sap_person_uuid'],
        'fields': [
            'name', 'first_name', 'short_name', 'abbreviation',
            'sap_ref', 'sap_person_uuid', 'stam_boek_nr',
            'gender', 'birth_date',
            'reg_start_date', 'reg_end_date', 'reg_inst_nr', 'reg_group_code',
            'email_cloud', 'email_private',
            'is_active',
        ],
        'references': {
            'person_type_id': {'model': 'myschool.person.type', 'key_field': 'name'},
        },
        'target_flag': 'sync_person',
        'priority': 40,
        'betask_object': 'PERSON',
    },

    # --- PropRelation (priority 50) ---
    {
        'model': 'myschool.proprelation',
        'natural_key': ['name'],
        'fields': [
            'name', 'is_active', 'is_administrative', 'is_organisational',
            'is_master', 'priority', 'start_date', 'end_date',
        ],
        'references': {
            'proprelation_type_id': {'model': 'myschool.proprelation.type', 'key_field': 'name'},
            'id_person': {'model': 'myschool.person', 'key_field': 'sap_person_uuid'},
            'id_person_child': {'model': 'myschool.person', 'key_field': 'sap_person_uuid'},
            'id_person_parent': {'model': 'myschool.person', 'key_field': 'sap_person_uuid'},
            'id_role': {'model': 'myschool.role', 'key_field': 'shortname'},
            'id_role_parent': {'model': 'myschool.role', 'key_field': 'shortname'},
            'id_role_child': {'model': 'myschool.role', 'key_field': 'shortname'},
            'id_org': {'model': 'myschool.org', 'key_field': 'sync_uuid'},
            'id_org_parent': {'model': 'myschool.org', 'key_field': 'sync_uuid'},
            'id_org_child': {'model': 'myschool.org', 'key_field': 'sync_uuid'},
            'id_period': {'model': 'myschool.period', 'key_field': 'name'},
            'id_period_parent': {'model': 'myschool.period', 'key_field': 'name'},
            'id_period_child': {'model': 'myschool.period', 'key_field': 'name'},
        },
        'target_flag': 'sync_proprelation',
        'priority': 50,
        'betask_object': 'PROPRELATION',
    },
]


def get_registry_by_model(model_name):
    """Return the registry entry for a given model name, or None."""
    for entry in SYNC_MODELS:
        if entry['model'] == model_name:
            return entry
    return None


def get_registry_by_betask_object(betask_object):
    """Return all registry entries matching a betask object name."""
    return [e for e in SYNC_MODELS if e['betask_object'] == betask_object]


def get_models_sorted_by_priority():
    """Return SYNC_MODELS sorted by priority (lowest first)."""
    return sorted(SYNC_MODELS, key=lambda e: e['priority'])
