from . import models
from . import wizard


def _fix_missing_references(env):
    """Assign references to any records that are missing one."""
    broken = env['activiteiten.record'].sudo().search([
        '|', ('name', '=', False), ('name', 'in', ['New', '', 'new']),
    ])
    for record in broken:
        record.name = env['ir.sequence'].sudo().next_by_code('activiteiten.record')
