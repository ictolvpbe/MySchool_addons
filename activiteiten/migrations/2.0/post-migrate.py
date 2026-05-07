import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Migratie naar 2.0: bus_price wordt een computed-stored field op basis
    van bus_ids.prijs. Voor bestaande activiteiten met een ingevulde bus_price
    moeten we die waarde verdelen over de bus-regels voor de compute draait,
    anders zet die bus_price op 0 (sum van een lege relatie).

    Strategie per activiteit met bus_price > 0:
      1. Haal aantal_bussen op (default '1').
      2. Zorg dat er minstens evenveel bus-regels zijn (auto-aanmaken).
      3. Verdeel bus_price gelijk over die regels door prijs in te vullen.
    """
    _logger.info('[activiteiten 2.0] migrating bus_price -> activiteiten.bus.prijs')

    # Veiligheidscheck: kolom moet bestaan voor we ermee aan de slag gaan.
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'activiteiten_bus' AND column_name = 'prijs'
    """)
    if not cr.fetchone():
        _logger.warning('[activiteiten 2.0] activiteiten_bus.prijs column does not exist yet, skipping')
        return

    # Vind alle activiteiten met een ingevulde bus_price
    cr.execute("""
        SELECT id, COALESCE(NULLIF(aantal_bussen, ''), '1') AS aantal, bus_price
        FROM activiteiten_record
        WHERE bus_price IS NOT NULL AND bus_price > 0
    """)
    rows = cr.fetchall()
    if not rows:
        _logger.info('[activiteiten 2.0] no records to migrate')
        return

    for activiteit_id, aantal_str, bus_price in rows:
        try:
            aantal = int(aantal_str)
        except (TypeError, ValueError):
            aantal = 1
        aantal = max(1, aantal)

        # Bestaande bus-regels ophalen
        cr.execute("""
            SELECT id, bus_nummer FROM activiteiten_bus
            WHERE activiteit_id = %s ORDER BY bus_nummer
        """, (activiteit_id,))
        existing = cr.fetchall()
        existing_nrs = {nr for _, nr in existing}

        # Ontbrekende bus-regels aanmaken
        nr = 1
        added = 0
        while len(existing) + added < aantal:
            if nr not in existing_nrs:
                cr.execute("""
                    INSERT INTO activiteiten_bus (activiteit_id, bus_nummer, create_uid, create_date, write_uid, write_date)
                    VALUES (%s, %s, 1, NOW() AT TIME ZONE 'UTC', 1, NOW() AT TIME ZONE 'UTC')
                """, (activiteit_id, nr))
                existing_nrs.add(nr)
                added += 1
            nr += 1

        # Verdeel bus_price gelijk
        prijs_per_bus = round(bus_price / aantal, 2)
        cr.execute("""
            UPDATE activiteiten_bus
            SET prijs = %s
            WHERE activiteit_id = %s AND (prijs IS NULL OR prijs = 0)
        """, (prijs_per_bus, activiteit_id))

    _logger.info(
        '[activiteiten 2.0] migrated bus_price for %d activiteiten records',
        len(rows),
    )
