from odoo import models, fields, api


class Taskboard(models.TransientModel):
    _name = 'myschool.taskboard'
    _description = 'Taskboard Dashboard Data Provider'

    @api.model
    def get_dashboard_data(self):
        """Return all data needed by the OWL taskboard component."""
        user = self.env.user
        user_group_ids = user.all_group_ids.ids

        # Tasks assigned to the current user
        my_tasks = self.env['myschool.process.task'].search([
            ('assigned_user_id', '=', user.id),
            ('state', 'not in', ['cancelled']),
        ])

        # Tasks assigned to user's groups (not yet claimed by someone)
        group_tasks = self.env['myschool.process.task'].search([
            ('assigned_group_id', 'in', user_group_ids),
            ('assigned_user_id', '=', False),
            ('state', 'not in', ['cancelled']),
        ])

        all_tasks = my_tasks | group_tasks

        # Build set of ready task IDs — a task is ready when all
        # preceding tasks (lower sequence in same instance) are done/cancelled.
        ready_ids = set()
        for task in all_tasks:
            if task.state in ('done', 'cancelled'):
                continue
            preceding_not_done = task.instance_id.task_ids.filtered(
                lambda t, seq=task.sequence, tid=task.id:
                    t.id != tid
                    and t.sequence < seq
                    and t.state not in ('done', 'cancelled')
            )
            if not preceding_not_done:
                ready_ids.add(task.id)

        def is_ready(t):
            return t.id in ready_ids

        # KPIs — only count tasks that are ready (predecessors done)
        today = fields.Date.today()
        kpis = {
            'my_tasks': len(my_tasks.filtered(lambda t: is_ready(t) and t.state != 'done')),
            'group_tasks': len(group_tasks.filtered(is_ready)),
            'overdue': len(all_tasks.filtered(
                lambda t: is_ready(t) and t.deadline and t.deadline < today and t.state not in ('done', 'cancelled')
            )),
            'done_today': len(my_tasks.filtered(
                lambda t: t.state == 'done'
                and t.date_done
                and t.date_done.date() == today
            )),
        }

        # Task lists by state — only show tasks whose predecessors are done
        def serialize_task(t):
            return {
                'id': t.id,
                'name': t.name,
                'description': t.description or '',
                'state': t.state,
                'process_name': t.instance_id.process_map_id.name or '',
                'instance_name': t.instance_id.name or '',
                'instance_id': t.instance_id.id,
                'assigned_user': t.assigned_user_id.name or '',
                'assigned_user_id': t.assigned_user_id.id or False,
                'assigned_group': t.assigned_group_id.name or '',
                'deadline': fields.Date.to_string(t.deadline) if t.deadline else '',
                'priority': t.priority,
                'is_overdue': t.is_overdue,
                'is_mine': t.assigned_user_id.id == user.id,
                'sequence': t.sequence,
            }

        ready_tasks = all_tasks.filtered(is_ready)

        tasks_todo = [serialize_task(t) for t in ready_tasks.filtered(
            lambda t: t.state == 'todo'
        ).sorted('sequence')]
        tasks_in_progress = [serialize_task(t) for t in ready_tasks.filtered(
            lambda t: t.state == 'in_progress'
        ).sorted('sequence')]
        tasks_done = [serialize_task(t) for t in all_tasks.filtered(
            lambda t: t.state == 'done'
        ).sorted(lambda t: t.date_done or t.write_date, reverse=True)[:20]]
        tasks_blocked = [serialize_task(t) for t in ready_tasks.filtered(
            lambda t: t.state == 'blocked'
        ).sorted('sequence')]

        # Active process instances
        active_instances = self.env['myschool.process.instance'].search([
            ('state', 'in', ['draft', 'running']),
            '|',
            ('started_by_id', '=', user.id),
            ('task_ids.assigned_user_id', '=', user.id),
        ], limit=10, order='create_date desc')

        instances = [{
            'id': inst.id,
            'name': inst.name,
            'process_name': inst.process_map_id.name,
            'state': inst.state,
            'progress': inst.progress,
            'task_count': inst.task_count,
            'start_date': fields.Datetime.to_string(inst.start_date) if inst.start_date else '',
        } for inst in active_instances]

        # Available process templates (approved)
        templates = self.env['myschool.process'].search([
            ('state', '=', 'approved'),
        ], order='name')
        template_list = [{
            'id': t.id,
            'name': t.name,
            'description': t.description or '',
            'step_count': len(t.step_ids.filtered(
                lambda s: s.step_type in ('task', 'subprocess')
            )),
        } for t in templates]

        # Check if user has processcomposer rights
        has_composer_access = user.has_group(
            'myschool_processcomposer.group_processcomposer_user'
        )

        return {
            'kpis': kpis,
            'tasks_todo': tasks_todo,
            'tasks_in_progress': tasks_in_progress,
            'tasks_done': tasks_done,
            'tasks_blocked': tasks_blocked,
            'instances': instances,
            'templates': template_list,
            'has_composer_access': has_composer_access,
        }
