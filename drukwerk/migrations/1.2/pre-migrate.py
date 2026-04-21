"""Remove the 'doorrekenen' state.

Any drukwerk.record still in state='doorrekenen' is moved to 'done' so
the new Selection (which no longer includes 'doorrekenen') stays valid.
Runs pre-migrate so no ORM load hits the old column value.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE drukwerk_record
           SET state = 'done'
         WHERE state = 'doorrekenen'
    """)
