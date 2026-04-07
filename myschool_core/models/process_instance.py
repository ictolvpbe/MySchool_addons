from odoo import models, fields, api
from odoo.exceptions import UserError


class MyschoolProcessInstance(models.Model):
    _name = 'myschool.process.instance'
    _description = 'Myschool Process Instance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Referentie', required=True, copy=False,
                       readonly=True, default='Nieuw')
    process_map_id = fields.Many2one('myschool.process', string='Procestemplate',
                                     required=True, ondelete='restrict')
    description = fields.Text(string='Beschrijving')
    state = fields.Selection([
        ('draft', 'Concept'),
        ('running', 'Actief'),
        ('completed', 'Voltooid'),
        ('cancelled', 'Geannuleerd'),
    ], string='Status', default='draft', required=True, tracking=True)

    started_by_id = fields.Many2one('res.users', string='Gestart door',
                                    default=lambda self: self.env.user,
                                    readonly=True)
    start_date = fields.Datetime(string='Startdatum')
    end_date = fields.Datetime(string='Einddatum')

    task_ids = fields.One2many('myschool.process.task', 'instance_id', string='Taken')
    task_count = fields.Integer(string='Aantal taken', compute='_compute_task_count')
    progress = fields.Float(string='Voortgang', compute='_compute_progress')

    @api.depends('task_ids')
    def _compute_task_count(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)

    @api.depends('task_ids.state')
    def _compute_progress(self):
        for rec in self:
            tasks = rec.task_ids.filtered(lambda t: t.state != 'cancelled')
            if tasks:
                done = len(tasks.filtered(lambda t: t.state == 'done'))
                rec.progress = (done / len(tasks)) * 100
            else:
                rec.progress = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nieuw') == 'Nieuw':
                vals['name'] = self.env['ir.sequence'].next_by_code('myschool.process.instance') or 'Nieuw'
        return super().create(vals_list)

    def action_start(self):
        for rec in self:
            if not rec.task_ids:
                raise UserError("Kan proces niet starten zonder taken.")
            rec.write({
                'state': 'running',
                'start_date': fields.Datetime.now(),
            })

    def action_complete(self):
        for rec in self:
            rec.write({
                'state': 'completed',
                'end_date': fields.Datetime.now(),
            })

    def action_cancel(self):
        for rec in self:
            rec.task_ids.filtered(
                lambda t: t.state not in ('done', 'cancelled')
            ).write({'state': 'cancelled'})
            rec.write({
                'state': 'cancelled',
                'end_date': fields.Datetime.now(),
            })

    def action_reset_to_draft(self):
        for rec in self:
            rec.write({
                'state': 'draft',
                'start_date': False,
                'end_date': False,
            })

    @api.model
    def create_from_template(self, process_map_id, description=''):
        """Create a process instance with tasks from a process map template."""
        process_map = self.env['myschool.process'].browse(process_map_id)
        if not process_map.exists():
            raise UserError("Procestemplate niet gevonden.")
        if process_map.state != 'approved':
            raise UserError("Alleen goedgekeurde processtemplates kunnen gestart worden.")

        instance = self.create({
            'process_map_id': process_map.id,
            'description': description or process_map.description,
        })

        task_steps = process_map.step_ids.filtered(
            lambda s: s.step_type in ('task', 'subprocess')
        )

        # Build sequence from connections (topological order)
        step_order = self._resolve_step_order(process_map, task_steps)

        Task = self.env['myschool.process.task']
        for seq, step in enumerate(step_order, start=1):
            group_id = False
            if step.lane_id and step.lane_id.role_id:
                # Try to find a res.groups linked to the role name
                group = self.env['res.groups'].search(
                    [('name', 'ilike', step.lane_id.role_id.name)], limit=1)
                if group:
                    group_id = group.id

            Task.create({
                'name': step.name,
                'description': step.description or '',
                'instance_id': instance.id,
                'step_id': step.id,
                'sequence': seq * 10,
                'assigned_group_id': group_id,
            })

        return instance.id

    def _resolve_step_order(self, process_map, task_steps):
        """Order task steps following the connection flow."""
        step_ids = set(task_steps.ids)
        # Build adjacency from connections
        next_map = {}
        for conn in process_map.connection_ids:
            src = conn.source_step_id.id
            tgt = conn.target_step_id.id
            next_map.setdefault(src, []).append(tgt)

        # BFS from start events through all steps
        start_steps = process_map.step_ids.filtered(lambda s: s.step_type == 'start')
        visited = []
        seen = set()
        queue = list(start_steps.ids)

        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if current in step_ids:
                visited.append(current)
            for nxt in next_map.get(current, []):
                if nxt not in seen:
                    queue.append(nxt)

        # Add any task steps not reached by BFS
        for step in task_steps:
            if step.id not in seen:
                visited.append(step.id)

        return self.env['myschool.process.step'].browse(visited)
