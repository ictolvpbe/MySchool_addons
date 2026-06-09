from odoo import models, fields


class MyschoolProjectProcessApply(models.TransientModel):
    """Wizard: voeg een proces (uit de Process Composer) in een project in.

    Elke task/subprocess-stap wordt een work item onder een phase-container
    met de procesnaam; de flow tussen stappen wordt ``depends_on_ids``.
    De echte logica leeft op ``myschool.project.apply_process``.
    """

    _name = 'myschool.project.process.apply'
    _description = 'Insert Process into Project'

    show_unapproved = fields.Boolean(
        string='Toon niet-goedgekeurde processen', default=False,
        help='Standaard zijn enkel goedgekeurde processen selecteerbaar.')
    process_id = fields.Many2one(
        'myschool.process', string='Process', required=True,
        help='Standaard enkel goedgekeurde processen; vink "Toon '
             'niet-goedgekeurde processen" aan voor de rest.')
    project_id = fields.Many2one(
        'myschool.project', string='Project', required=True)
    parent_id = fields.Many2one(
        'myschool.project.task', string='Under parent item',
        domain="[('project_id', '=', project_id)]",
        help='Optioneel: hang het proces onder een bestaand work item.')

    def action_apply(self):
        self.ensure_one()
        self.project_id.apply_process(
            self.process_id, self.parent_id.id if self.parent_id else False)
        return {'type': 'ir.actions.act_window_close'}
