def migrate(cr, version):
    """Remove obsolete 'interne_opvolging' subtype — convert existing records to NULL."""
    cr.execute("""
        UPDATE professionalisering_record
           SET subtype_individueel = NULL
         WHERE subtype_individueel = 'interne_opvolging'
    """)
