"""Fix empty action names for Dutch (nl_BE) users.

The name field on ir.actions is translate=True (JSONB).  The XML only sets
the en_US value.  If no nl_BE key exists, the Odoo action loader returns
an empty name → "Naamloos".  This script copies the en_US value into every
missing language key.
"""


def migrate(cr, version):
    _fix_action('ir_act_client', 'action_myschool_dashboard_client', 'Aanvragen', cr)
    _fix_action('ir_act_window', 'action_myschool_dashboard', 'Aanvragen', cr)
    _fix_action('ir_act_window', 'action_open_activiteiten_list', 'Activiteiten', cr)
    _fix_action('ir_act_window', 'action_open_professionalisering', 'Professionalisering', cr)


def _fix_action(table, xmlid_name, label, cr):
    model = 'ir.actions.client' if table == 'ir_act_client' else 'ir.actions.act_window'

    # Get the database id and current installed languages
    cr.execute("""
        SELECT d.res_id
          FROM ir_model_data d
         WHERE d.module = 'myschool_dashboard'
           AND d.name   = %s
           AND d.model  = %s
    """, [xmlid_name, model])
    row = cr.fetchone()
    if not row:
        return
    res_id = row[0]

    cr.execute("SELECT code FROM res_lang WHERE active = true")
    langs = [r[0] for r in cr.fetchall()]

    # Build a JSONB object with the label for every active language
    name_obj = {lang: label for lang in langs}
    name_obj['en_US'] = label  # always include source language

    import json
    name_json = json.dumps(name_obj)

    # Update both the specific action table and the base ir_actions table
    for tbl in (table, 'ir_actions'):
        cr.execute(
            f"UPDATE {tbl} SET name = %s::jsonb WHERE id = %s",
            [name_json, res_id],
        )
