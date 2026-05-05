#from . import app
from . import allowed_schools_mixin
from . import org_type
from . import org
from . import person_type
from . import person
from . import person_details
from . import role_type
from . import role
from . import period_type
from . import period
from . import proprelation_type
from . import proprelation
from . import proprelation_service
from . import config_item
from . import ci_relation
from . import field_template
from . import betask_type
from . import betask_type_service
from . import betask
from . import betask_service
from . import betask_processor
from . import manual_task_service
from . import manual_task_processor
from . import sys_event_type
from . import sys_event_type_service
from . import sys_event
from . import sys_event_service

from . import informat_service
from . import informat_service_config
from . import informat_dto
from . import smartschool_service
from . import ldap_server_config
from . import ldap_service
from . import res_company
from . import res_users

# Process models
from . import process
from . import process_lane
from . import process_lane_preset
from . import process_step
from . import process_connection
from . import process_version
from . import process_field
from . import process_instance
from . import process_task

# Asset models
from . import asset_type_category
from . import asset_type
from . import asset
from . import asset_license
from . import asset_checkout
from . import access_policy


# Base/independent models first
# BeTask models (be_task_type must come before be_task)



# Service models (these are AbstractModels - no database tables)
# They must be imported AFTER the models they depend on
#from . import informat_dto
#from . import informat_service_config
#from . import informat_service