from . import models
from . import controllers


def _migrate_legacy_group_flags_post_init(env):
    """One-shot upgrade hook: roll legacy BRSO/role group-flags into the
    target org's ``has_comgroup`` / ``has_secgroup`` / ``has_odoo_group``
    + ``odoo_group_ids``. Safe to run on fresh installs (no-op when
    legacy columns don't exist).

    Also normalises legacy "placeholder" values that block UNIQUE
    indexes from being created on upgrade — see ``_normalise_legacy_placeholders``.
    """
    try:
        env['myschool.org']._migrate_group_flags_from_legacy()
    except Exception:
        # Don't block installation on migration trouble — operators can
        # run it manually from the Sync Test Session button afterwards.
        env['ir.logging'].sudo().create({
            'name': 'myschool_core.migrate',
            'type': 'server',
            'level': 'WARNING',
            'message': 'Legacy group-flag migration raised; run manually if needed.',
            'path': '__init__',
            'func': '_migrate_legacy_group_flags_post_init',
            'line': '0',
        })

    try:
        _normalise_legacy_placeholders(env)
    except Exception as e:
        env['ir.logging'].sudo().create({
            'name': 'myschool_core.migrate',
            'type': 'server',
            'level': 'WARNING',
            'message': f'Legacy placeholder cleanup raised: {e}',
            'path': '__init__',
            'func': '_normalise_legacy_placeholders',
            'line': '0',
        })


def _normalise_legacy_placeholders(env):
    """Convert legacy ``"0"`` placeholders to NULL so UNIQUE indexes
    can be created.

    Background: an older import path wrote literal ``"0"`` for empty
    SAP-shortnames on BACKEND roles. Because ``shortname`` carries a
    UNIQUE constraint, those rows blocked the index creation on
    upgrade with a "Key (shortname)=(0) is duplicated." schema log.

    This is idempotent and a no-op when no offending rows exist.
    """
    cr = env.cr
    cr.execute("""
        UPDATE myschool_role
           SET shortname = NULL
         WHERE shortname = '0'
    """)
    if cr.rowcount:
        env['ir.logging'].sudo().create({
            'name': 'myschool_core.migrate',
            'type': 'server',
            'level': 'INFO',
            'message': (
                f'Normalised {cr.rowcount} legacy myschool_role.shortname '
                f'value(s) "0" → NULL to unblock UNIQUE index'),
            'path': '__init__',
            'func': '_normalise_legacy_placeholders',
            'line': '0',
        })
