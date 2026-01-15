#from . import app
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
from . import config_item
from . import ci_relation
from . import betask_type
from . import betask_type_service
from . import betask
from . import betask_service
from . import betask_processor
from . import sys_event_type
from . import sys_event_type_service
from . import sys_event
from . import sys_event_service

from . import informat_service
from . import informat_service_config
from . import informat_dto
from . import smartschool_service


# Base/independent models first
# BeTask models (be_task_type must come before be_task)



# Service models (these are AbstractModels - no database tables)
# They must be imported AFTER the models they depend on
#from . import informat_dto
#from . import informat_service_config
#from . import informat_service