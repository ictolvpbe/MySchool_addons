"""Verwijder de dode EMPLOYEE/STUDENT betask-types (LDAP + DB).

Legacy sporen, vervangen door de generieke ``LDAP/USER/*`` (AD-accounts) en
``DB/PERSON/*`` (database) sporen: geen creatie meer, 0 instanties. De
DB-records waren grotendeels xmlid-loze wezen (ooit runtime / door de
inmiddels verwijderde ``ensure_standard_types``-seeder gemaakt), dus het
schrappen van de data-definities (betask_data.xml) ruimt ze niet op — vandaar
deze migratie.

Geguard op 0 instanties: een type met betasks wordt NOOIT verwijderd.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
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
