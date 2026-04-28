def migrate(cr, version):
    """Replace deprecated subtype values + simplify state flow (no more bevestiging step)."""
    cr.execute("""
        UPDATE professionalisering_record
           SET subtype_individueel = 'nascholing'
         WHERE subtype_individueel IN ('cursus', 'workshop')
    """)
    cr.execute("""
        UPDATE professionalisering_record
           SET state = 'done'
         WHERE state = 'bevestiging'
    """)
