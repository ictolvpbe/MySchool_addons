"""Migreer bestaande records van het oude Selection-veld 'vak' naar de
nieuwe Many2one 'vak_id' die naar professionalisering.vak verwijst.

Het oude 'vak' (VARCHAR) blijft aanwezig in de DB tot ORM hem opruimt;
we lezen z'n waarden en mappen ze naar vak.id via XML-id lookup."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Build a dict: old Selection-key (= vak.code) → new vak.id
    cr.execute("""
        SELECT v.id, v.code
        FROM professionalisering_vak v
    """)
    code_to_id = {code: vak_id for vak_id, code in cr.fetchall()}

    if not code_to_id:
        _logger.warning(
            "professionalisering.vak migration: geen vak-records gevonden, "
            "data file is mogelijk niet geladen.")
        return

    # Check of de oude kolom 'vak' nog bestaat
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'professionalisering_record' AND column_name = 'vak'
    """)
    if not cr.fetchone():
        _logger.info("professionalisering.vak migration: oude kolom 'vak' "
                     "bestaat niet meer, niets te migreren.")
        return

    # Per code, update alle records met die oude waarde
    updated = 0
    for code, vak_id in code_to_id.items():
        cr.execute(
            "UPDATE professionalisering_record SET vak_id = %s "
            "WHERE vak = %s AND vak_id IS NULL",
            (vak_id, code),
        )
        updated += cr.rowcount

    _logger.info(
        "professionalisering.vak migration: %d records gemigreerd naar "
        "vak_id (van %d beschikbare vak-codes).",
        updated, len(code_to_id),
    )

    # Old VARCHAR kolom 'vak' opruimen — niet meer gebruikt na deze migratie.
    # Odoo zou hem niet automatisch droppen, dus dat doen we hier expliciet.
    cr.execute("ALTER TABLE professionalisering_record DROP COLUMN IF EXISTS vak")
