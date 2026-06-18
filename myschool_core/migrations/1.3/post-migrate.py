# -*- coding: utf-8 -*-
"""Migratie 1.1 — twee onafhankelijke opkuisstappen.

1. Verwijder de dode EMPLOYEE/STUDENT betask-types (LDAP + DB). Legacy sporen,
   vervangen door de generieke ``LDAP/USER/*`` (AD-accounts) en ``DB/PERSON/*``
   (database) sporen: geen creatie meer, 0 instanties. De DB-records waren
   grotendeels xmlid-loze wezen, dus het schrappen van de data-definities
   (betask_data.xml) ruimt ze niet op — vandaar deze migratie. Geguard op 0
   instanties: een type met betasks wordt NOOIT verwijderd.

2. Verhuis de SAP-sync safeguard-drempels van ``myschool.informat.service.config``
   naar het neutrale kernel-model ``myschool.sap.sync.config`` (slice 3 /
   connector-naden-refactor). Odoo dropt verwijderde kolommen niet automatisch,
   dus de oude waarden staan bij een upgrade nog rauw in de oude tabel. We nemen
   ze (best-effort) over. Defaults dekken "geen oude rij / verse DB".
"""

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

_THRESHOLD_FIELDS = (
    'safeguard_enabled',
    'threshold_person_pct',
    'threshold_org_pct',
    'threshold_orggroup_pct',
    'threshold_proprelation_pct',
    'safeguard_min_changes',
)


def _drop_dead_betask_types(cr):
    # Eventuele xmlid-koppelingen van de verwijderde data-definities opruimen.
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'myschool_core'
          AND model = 'myschool.betask.type'
          AND name IN ('betask_type_ldap_student_add',
                       'betask_type_ldap_employee_add',
                       'betask_type_ldap_employee_upd',
                       'betask_type_db_student_add',
                       'betask_type_db_student_update',
                       'betask_type_db_employee_add',
                       'betask_type_db_employee_upd')
    """)

    # De type-records zelf wissen — uitsluitend wanneer ze 0 betasks hebben.
    # Dekt LDAP/EMPLOYEE·STUDENT en DB/EMPLOYEE·STUDENT (incl. varianten zoals
    # DB/EMPLOYEE/UPD-PROP). USER/* en PERSON/* blijven ongemoeid.
    cr.execute("""
        DELETE FROM myschool_betask_type bt
        WHERE bt.target IN ('LDAP', 'DB')
          AND bt.object IN ('EMPLOYEE', 'STUDENT')
          AND NOT EXISTS (
              SELECT 1 FROM myschool_betask b WHERE b.betasktype_id = bt.id
          )
    """)
    _logger.info(
        "migr 1.1: %s dode EMPLOYEE/STUDENT betask-type(s) (LDAP+DB) verwijderd",
        cr.rowcount)


def _migrate_safeguard_thresholds(cr):
    # Bestaat de oude tabel + (minstens één) kolom nog?
    cr.execute("SELECT to_regclass('public.myschool_informat_service_config')")
    if not cr.fetchone()[0]:
        return

    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'myschool_informat_service_config'
           AND column_name = ANY(%s)
        """,
        (list(_THRESHOLD_FIELDS),),
    )
    present = [r[0] for r in cr.fetchall()]
    if not present:
        return

    cols = ', '.join(present)
    cr.execute(
        "SELECT %s FROM myschool_informat_service_config "
        "WHERE active = true ORDER BY id LIMIT 1" % cols
    )
    row = cr.fetchone()
    if not row:
        return

    old_vals = dict(zip(present, row))
    # Niets te doen als alles nog op None staat.
    if all(v is None for v in old_vals.values()):
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    config = env['myschool.sap.sync.config'].get_config()
    write_vals = {k: v for k, v in old_vals.items() if v is not None}
    if write_vals:
        config.write(write_vals)
        _logger.info(
            "Migratie 1.1: safeguard-drempels overgezet naar "
            "myschool.sap.sync.config: %s", write_vals
        )


def migrate(cr, version):
    _drop_dead_betask_types(cr)
    _migrate_safeguard_thresholds(cr)
