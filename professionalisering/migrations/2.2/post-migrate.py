def migrate(cr, version):
    """Convert legacy `adres` Char to professionalisering.address records."""

    # 0) Drop the obsolete UNIQUE(name) constraint if it still exists
    cr.execute("""
        ALTER TABLE professionalisering_address
        DROP CONSTRAINT IF EXISTS professionalisering_address_name_unique
    """)

    # 1) Convert legacy adres column (if still exists)
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'professionalisering_record' AND column_name = 'adres'
    """)
    if not cr.fetchone():
        return

    cr.execute("""
        SELECT DISTINCT TRIM(adres) FROM professionalisering_record
        WHERE adres IS NOT NULL AND TRIM(adres) != ''
    """)
    for (addr,) in cr.fetchall():
        cr.execute(
            "INSERT INTO professionalisering_address "
            "(name, active, create_uid, create_date, write_uid, write_date) "
            "VALUES (%s, true, 1, NOW(), 1, NOW())",
            (addr,),
        )

    cr.execute("""
        UPDATE professionalisering_record r
           SET address_id = a.id
          FROM professionalisering_address a
         WHERE TRIM(r.adres) = a.name
           AND r.address_id IS NULL
    """)

    cr.execute("ALTER TABLE professionalisering_record DROP COLUMN IF EXISTS adres")
