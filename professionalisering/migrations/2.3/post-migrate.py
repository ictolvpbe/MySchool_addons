import json
import os


def migrate(cr, version):
    """Seed structured address data from the cleaned Excel input + set
    location_type on existing prof records based on linked address."""

    # 1) Set location_type on existing prof records
    cr.execute("""
        UPDATE professionalisering_record r
           SET location_type = CASE WHEN a.is_online THEN 'online' ELSE 'address' END
          FROM professionalisering_address a
         WHERE r.address_id = a.id
           AND r.location_type IS NULL
    """)
    cr.execute("""
        UPDATE professionalisering_record
           SET location_type = 'address'
         WHERE location_type IS NULL
    """)

    # 2) Seed test addresses (only if no addresses present)
    cr.execute("SELECT COUNT(*) FROM professionalisering_address")
    if cr.fetchone()[0] > 0:
        return

    json_path = os.path.join(os.path.dirname(__file__), 'test_addresses.json')
    if not os.path.exists(json_path):
        return

    with open(json_path) as f:
        addresses = json.load(f)

    cr.execute("SELECT id FROM res_country WHERE code = 'BE' LIMIT 1")
    row = cr.fetchone()
    be_country_id = row[0] if row else None

    for a in addresses:
        cr.execute(
            "INSERT INTO professionalisering_address ("
            "  name, organization, is_online, "
            "  street, number, postal_code, city, country_id, "
            "  billing_street, billing_postal_code, "
            "  active, create_uid, create_date, write_uid, write_date"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, 1, NOW(), 1, NOW())",
            (
                a['name'],
                a['organization'] or None,
                a['is_online'],
                a['street'] or None,
                a['number'] or None,
                a['postal_code'] or None,
                a['city'] or None,
                None if a['is_online'] else be_country_id,
                a['billing_street'] or None,
                a['billing_postal_code'] or None,
            ),
        )
