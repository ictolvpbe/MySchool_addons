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

    try:
        _seed_type_icon_defaults(env)
    except Exception as e:
        env['ir.logging'].sudo().create({
            'name': 'myschool_core.migrate',
            'type': 'server',
            'level': 'WARNING',
            'message': f'Type-icon seeding raised: {e}',
            'path': '__init__',
            'func': '_seed_type_icon_defaults',
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


# Default Font Awesome classes + colours per canonical type name.
# Only applied when the type record exists and the corresponding field
# is still empty — so admins can override via the form view without
# later upgrades clobbering their choice.
_ORG_TYPE_ICON_DEFAULTS = {
    'SCHOOLBOARD': {'fa': 'fa fa-university',     'color': '#7c3aed'},  # purple
    'SCHOOL':      {'fa': 'fa fa-graduation-cap', 'color': '#0284c7'},  # blue
    'DEPARTMENT':  {'fa': 'fa fa-sitemap',        'color': '#0d9488'},  # teal
    'PERSONGROUP': {'fa': 'fa fa-users',          'color': '#d97706'},  # amber
}
_PERSON_TYPE_ICON_DEFAULTS = {
    # Persons keep their initials avatar; we only seed a colour so the
    # avatar-circle bg tints by type. The frontend draws initials on top
    # whenever both icon_image and icon_fa_class are empty.
    'STUDENT':  {'fa': '', 'color': '#0d9488'},   # teal — matches huidige
    'EMPLOYEE': {'fa': '', 'color': '#0284c7'},   # blue — matches huidige
    'RELATION': {'fa': '', 'color': '#9333ea'},   # violet
}


def _seed_type_icon_defaults(env):
    """Idempotent seed of sensible per-type icon defaults. Skips fields
    that already have a non-empty value, so admin choices stick across
    upgrades.
    """
    if 'myschool.org.type' in env:
        OrgType = env['myschool.org.type']
        for name, spec in _ORG_TYPE_ICON_DEFAULTS.items():
            rec = OrgType.search([('name', '=', name)], limit=1)
            if not rec:
                continue
            if spec.get('fa') and not rec.icon_fa_class:
                rec.icon_fa_class = spec['fa']
            if spec.get('color') and not rec.icon_color:
                rec.icon_color = spec['color']
    if 'myschool.person.type' in env:
        PersonType = env['myschool.person.type']
        for name, spec in _PERSON_TYPE_ICON_DEFAULTS.items():
            rec = PersonType.search([('name', '=', name)], limit=1)
            if not rec:
                continue
            if spec.get('fa') and not rec.icon_fa_class:
                rec.icon_fa_class = spec['fa']
            if spec.get('color') and not rec.icon_color:
                rec.icon_color = spec['color']
