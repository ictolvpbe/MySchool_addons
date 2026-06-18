# -*- coding: utf-8 -*-
"""Bump CLOUD/GROUPMEMBER/ADD priority above CLOUD/USER/ADD.

``cloud_task_types.xml`` shipped CLOUD/USER/ADD and CLOUD/GROUPMEMBER/ADD
both at priority 20. Since the betask processor orders only by priority,
the Google group-membership task could run before the Google account
existed, failing with "user not found" — the same class of bug fixed for
LDAP (where USER=40 < GROUPMEMBER=45). The XML is noupdate=1, so an
upgrade won't re-prioritise an already-loaded type; this migration does
it. Idempotent, keyed on (target, object, action).
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "UPDATE myschool_betask_type SET priority=25 "
        "WHERE target='CLOUD' AND object='GROUPMEMBER' AND action='ADD' "
        "AND priority < 25"
    )
    if cr.rowcount:
        _logger.info(
            '[1.4] CLOUD/GROUPMEMBER/ADD priority -> 25 (was < CLOUD/USER/ADD)')
