"""Bestaande records: zet vervoer_type op basis van bus_nodig.
Voor records waar bus_nodig=True → 'bus'. Anders → 'anders' (gebruiker kan
later aanpassen naar openbaar_vervoer / te_voet / fiets / auto)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE activiteiten_record
        SET vervoer_type = CASE
            WHEN bus_nodig THEN 'bus'
            ELSE 'anders'
        END
        WHERE vervoer_type IS NULL
    """)
