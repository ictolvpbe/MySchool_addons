from odoo import models, fields, api


class MyschoolProcessTask(models.Model):
    _name = 'myschool.process.task'
    _description = 'Myschool Process Task'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char(string='Taaknaam', required=True, tracking=True)
    description = fields.Text(string='Beschrijving')
    instance_id = fields.Many2one('myschool.process.instance', string='Procesinstantie',
                                  required=True, ondelete='cascade')
    step_id = fields.Many2one('myschool.process.step', string='Processtap',
                              ondelete='set null')
    process_map_id = fields.Many2one(related='instance_id.process_map_id',
                                     string='Procestemplate', store=True)

    state = fields.Selection([
        ('todo', 'Te doen'),
        ('in_progress', 'Bezig'),
        ('done', 'Voltooid'),
        ('cancelled', 'Geannuleerd'),
        ('blocked', 'Geblokkeerd'),
    ], string='Status', default='todo', required=True, tracking=True)

    assigned_user_id = fields.Many2one('res.users', string='Toegewezen aan',
                                       tracking=True)
    assigned_group_id = fields.Many2one('res.groups', string='Groep')

    deadline = fields.Date(string='Deadline')
    priority = fields.Selection([
        ('0', 'Normaal'),
        ('1', 'Laag'),
        ('2', 'Hoog'),
        ('3', 'Urgent'),
    ], string='Prioriteit', default='0')

    sequence = fields.Integer(string='Volgorde', default=10)
    notes = fields.Html(string='Notities')
    color = fields.Integer(string='Kleur')

    date_start = fields.Datetime(string='Startdatum', readonly=True)
    date_done = fields.Datetime(string='Afgerond op', readonly=True)

    is_overdue = fields.Boolean(string='Verlopen', compute='_compute_is_overdue')
    is_ready = fields.Boolean(string='Klaar om te starten', compute='_compute_is_ready')
    instance_state = fields.Selection(related='instance_id.state', string='Processtatus')

    @api.depends('sequence', 'instance_id.task_ids.state', 'instance_id.task_ids.sequence', 'state')
    def _compute_is_ready(self):
        for task in self:
            if task.state in ('done', 'cancelled'):
                task.is_ready = False
                continue
            my_seq = task.sequence
            preceding = task.instance_id.task_ids.filtered(
                lambda t, seq=my_seq: t.sequence < seq
                and t.state not in ('done', 'cancelled')
            )
            task.is_ready = not preceding

    @api.depends('deadline', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for task in self:
            task.is_overdue = (
                task.deadline
                and task.deadline < today
                and task.state not in ('done', 'cancelled')
            )

    def action_start(self):
        self.write({
            'state': 'in_progress',
            'date_start': fields.Datetime.now(),
        })

    def action_done(self):
        self.write({
            'state': 'done',
            'date_done': fields.Datetime.now(),
        })
        # Auto-complete process if all tasks done
        for task in self:
            instance = task.instance_id
            pending = instance.task_ids.filtered(
                lambda t: t.state not in ('done', 'cancelled')
            )
            if not pending and instance.state == 'running':
                instance.action_complete()

    def action_reset(self):
        self.write({
            'state': 'todo',
            'date_start': False,
            'date_done': False,
        })

    def action_block(self):
        self.write({'state': 'blocked'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_assign_to_me(self):
        self.write({'assigned_user_id': self.env.uid})

    @api.model
    def update_task_state(self, task_id, new_state):
        """Called from OWL frontend to update task state via drag-and-drop."""
        task = self.browse(task_id)
        if not task.exists():
            return False
        if new_state == 'in_progress' and not task.date_start:
            task.action_start()
        elif new_state == 'done':
            task.action_done()
        elif new_state == 'todo':
            task.action_reset()
        elif new_state == 'blocked':
            task.action_block()
        else:
            task.state = new_state
        return True
