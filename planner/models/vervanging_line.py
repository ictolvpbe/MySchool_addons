from odoo import models, fields, api
from odoo.exceptions import UserError


class PlannerVervangingLine(models.Model):
    _name = 'planner.vervanging.line'
    _description = 'Vervanging per leerkracht'

    planner_id = fields.Many2one(
        'planner.record', string='Inhaalplan',
        required=True, ondelete='cascade',
    )
    leerkracht_id = fields.Many2one(
        'hr.employee', string='Leerkracht (afwezig)',
        required=True,
    )
    vervanger_id = fields.Many2one(
        'hr.employee', string='Vervanger',
        required=True,
    )
    inhaal_datum = fields.Datetime(
        related='planner_id.inhaal_datum',
        string='Datum',
        store=True,
    )
    inhaal_datum_end = fields.Datetime(
        related='planner_id.inhaal_datum_end',
        string='Einde',
        store=True,
    )
    planner_state = fields.Selection(
        related='planner_id.state',
        string='Status',
        store=True,
    )

    @api.constrains('leerkracht_id', 'vervanger_id', 'planner_id')
    def _check_vervanger(self):
        for line in self:
            # Substitute cannot be one of the absent teachers
            if line.planner_id.leerkracht_id and line.vervanger_id == line.planner_id.leerkracht_id:
                raise UserError(
                    f"{line.vervanger_id.display_name} is zelf afwezig "
                    f"en kan dus niet als vervanger ingepland worden."
                )
            # Substitute cannot already be assigned on the same date
            if line.planner_id.inhaal_datum:
                date = line.planner_id.inhaal_datum.date()
                conflicts = self.search([
                    ('id', '!=', line.id),
                    ('vervanger_id', '=', line.vervanger_id.id),
                    ('planner_id.inhaal_datum', '>=', f'{date} 00:00:00'),
                    ('planner_id.inhaal_datum', '<=', f'{date} 23:59:59'),
                ])
                if conflicts:
                    raise UserError(
                        f"{line.vervanger_id.display_name} is al als vervanger ingepland "
                        f"op {date.strftime('%d/%m/%Y')} voor een ander inhaalmoment."
                    )
