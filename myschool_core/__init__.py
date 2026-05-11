from . import models
from . import controllers


def _migrate_legacy_group_flags_post_init(env):
    """One-shot upgrade hook: roll legacy BRSO/role group-flags into the
    target org's ``has_comgroup`` / ``has_secgroup`` / ``has_odoo_group``
    + ``odoo_group_ids``. Safe to run on fresh installs (no-op when
    legacy columns don't exist)."""
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
