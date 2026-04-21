"""Rename existing drukwerk.record entries that are still stuck on 'New'.

Older installs could end up with name='New' when the ir.sequence was
scoped to a different company than the creating user. Assign a fresh
DWK-xxxx reference to each of those records using the shared sequence.
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    seq = env['ir.sequence'].sudo().search(
        [('code', '=', 'drukwerk.record')], limit=1,
    )
    if not seq:
        return

    if seq.company_id:
        seq.write({'company_id': False})

    cr.execute("""
        SELECT id
          FROM drukwerk_record
         WHERE name = 'New' OR name IS NULL OR name = ''
      ORDER BY id
    """)
    ids = [row[0] for row in cr.fetchall()]
    if not ids:
        return

    cr.execute("""
        SELECT MAX(
            CAST(NULLIF(REGEXP_REPLACE(name, '^DWK-', ''), '') AS INTEGER)
        )
          FROM drukwerk_record
         WHERE name LIKE 'DWK-%%'
    """)
    row = cr.fetchone()
    last_number = (row and row[0]) or 0
    if seq.number_next <= last_number:
        seq.write({'number_next': last_number + 1})

    records = env['drukwerk.record'].browse(ids)
    for record in records:
        record.name = seq._next()
