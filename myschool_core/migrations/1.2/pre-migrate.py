# -*- coding: utf-8 -*-
"""Fix LDAP betask-type processing priorities + adopt them into XML data.

``data/ldap_task_types.xml`` was commented out of the manifest, so every
LDAP betask type was born at the model default priority (10) via the
runtime ``betask.type.service.get_or_create``. With USER/GROUP/GROUPMEMBER
all at priority 10 the processor (``find_auto_process_types`` orders by
priority only) had no guaranteed order — and GROUPMEMBER/ADD could, and in
practice did, run *before* USER/ADD: the AD account didn't exist yet, so
``process_ldap_groupmember_add`` failed with "User not found in LDAP" while
USER/ADD completed a couple of seconds later. The unrelated cloud /
smartschool / letter type XMLs *were* loaded, which is why only LDAP lacked
a sane gradient.

The companion change re-enables ``data/ldap_task_types.xml`` in the
manifest (priorities GROUP=35, USER=40, GROUPMEMBER=45 → user/group always
before membership). This pre-migration runs BEFORE that XML loads and, for
each LDAP type that already exists, (a) sets the intended priority and
(b) binds the canonical xmlid, so the noupdate XML *adopts* the existing
row instead of tripping the UNIQUE(target, object, action) constraint with
a duplicate insert. Types that don't exist yet are left for the XML to
create fresh. Idempotent and re-runnable.
"""
import logging

_logger = logging.getLogger(__name__)

# (xmlid, target, object, action, priority) — mirrors data/ldap_task_types.xml
LDAP_TYPES = [
    ('betasktype_ldap_user_add',           'LDAP', 'USER',        'ADD',    40),
    ('betasktype_ldap_user_upd',           'LDAP', 'USER',        'UPD',    41),
    ('betasktype_ldap_user_deact',         'LDAP', 'USER',        'DEACT',  42),
    ('betasktype_ldap_user_del',           'LDAP', 'USER',        'DEL',    43),
    ('betasktype_ldap_group_add',          'LDAP', 'GROUP',       'ADD',    35),
    ('betasktype_ldap_group_upd',          'LDAP', 'GROUP',       'UPD',    36),
    ('betasktype_ldap_group_deact',        'LDAP', 'GROUP',       'DEACT',  37),
    ('betasktype_ldap_group_del',          'LDAP', 'GROUP',       'DEL',    38),
    ('betasktype_ldap_groupmember_add',    'LDAP', 'GROUPMEMBER', 'ADD',    45),
    ('betasktype_ldap_groupmember_remove', 'LDAP', 'GROUPMEMBER', 'REMOVE', 46),
]


def migrate(cr, version):
    for xmlid, target, obj, action, priority in LDAP_TYPES:
        cr.execute(
            "SELECT id FROM myschool_betask_type "
            "WHERE target=%s AND object=%s AND action=%s",
            (target, obj, action),
        )
        row = cr.fetchone()
        if not row:
            # Doesn't exist yet — the re-enabled XML will create it
            # with the correct priority on this same upgrade.
            continue
        type_id = row[0]

        cr.execute(
            "UPDATE myschool_betask_type SET priority=%s WHERE id=%s",
            (priority, type_id),
        )

        # Bind the canonical xmlid (once) so the noupdate XML adopts this
        # existing row rather than inserting a duplicate that would break
        # the UNIQUE(target, object, action) constraint.
        cr.execute(
            "SELECT id FROM ir_model_data "
            "WHERE module='myschool_core' AND name=%s",
            (xmlid,),
        )
        if cr.fetchone():
            continue
        cr.execute(
            "INSERT INTO ir_model_data "
            "(module, name, model, res_id, noupdate) "
            "VALUES ('myschool_core', %s, 'myschool.betask.type', %s, true)",
            (xmlid, type_id),
        )
        _logger.info(
            '[1.2] LDAP type %s/%s/%s (id=%s): priority=%s, bound xmlid %s',
            target, obj, action, type_id, priority, xmlid)
