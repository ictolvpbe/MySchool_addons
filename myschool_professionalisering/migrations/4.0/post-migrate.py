"""Migratie 4.0: bestaande carpool=True records krijgen vervoersmiddel='auto_carpool'.

Reden: nieuw veld 'vervoersmiddel' (Selection) vervangt de zichtbare carpool Boolean.
Bestaande records met carpool=True moeten consistent blijven na de upgrade.
"""

def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE professionalisering_record
           SET vervoersmiddel = 'auto_carpool'
         WHERE carpool = True
           AND (vervoersmiddel IS NULL OR vervoersmiddel = '')
    """)
