# -*- coding: utf-8 -*-
"""Migratie 1.1 — verhuis de SAP-sync safeguard-drempels.

De threshold-/safeguard-velden zijn van ``myschool.informat.service.config``
naar het neutrale kernel-model ``myschool.sap.sync.config`` verplaatst
(slice 3 / connector-naden-refactor). Odoo dropt verwijderde kolommen niet
automatisch, dus de oude waarden staan bij een upgrade nog rauw in de tabel
``myschool_informat_service_config``. We nemen ze (best-effort) over in de
nieuwe config-rij. Defaults dekken het geval "geen oude rij / verse DB".
"""

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

_FIELDS = (
    'safeguard_enabled',
    'threshold_person_pct',
    'threshold_org_pct',
    'threshold_orggroup_pct',
    'threshold_proprelation_pct',
    'safeguard_min_changes',
)


def migrate(cr, version):
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
        (list(_FIELDS),),
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
