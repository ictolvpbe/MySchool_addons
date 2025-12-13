from odoo import models, fields, api


class BeTaskType(models.Model):
    _name = 'myschool.betask.type'
    _description = 'BeTask Type'

    name = fields.Char(
        string='Name',
        required=True,
        index=True,
        unique=True
    )
    target = fields.Char(
        string='Target',
        required=True,
        help='DB, AD, CLOUD, etc.'
    )
    object = fields.Char(
        string='Object',
        required=True,
        help='ORG, PERSON, etc.'
    )
    action = fields.Char(
        string='Action',
        required=True,
        help='ADD, UPD, DEACT, ARC, DEL'
    )

    # Relations
    task_ids = fields.One2many(
        'myschool.betask.task',
        'betasktype_id',
        string='Tasks'
    )

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'The task type name must be unique!')
    ]


class BeTaskStatus(models.Model):
    """Status enumeration for BeTask"""
    _name = 'myschool.betask.status'
    _description = 'BeTask Status'

    name = fields.Selection([
        ('new', 'NEW'),
        ('processing', 'PROCESSING'),
        ('completed_ok', 'COMPLETED_OK'),
        ('error', 'ERROR'),
    ], string='Status', required=True)


class BeTask(models.Model):
    _name = 'myschool.betask.task'
    _description = 'BeTask'
    _order = 'lastrun desc, id desc'

    automatic_sync = fields.Boolean(
        string='Automatic Sync',
        default=True,
        required=True
    )
    betasktype_id = fields.Many2one(
        'myschool.betask.type',
        string='Task Type',
        required=True,
        ondelete='restrict',
        index=True
    )
    data = fields.Text(
        string='Data'
    )
    data2 = fields.Text(
        string='Data 2'
    )
    status = fields.Selection([
        ('new', 'NEW'),
        ('processing', 'PROCESSING'),
        ('completed_ok', 'COMPLETED_OK'),
        ('error', 'ERROR'),
    ], string='Status', required=True, default='new', index=True)

    lastrun = fields.Datetime(
        string='Last Run'
    )
    error_description = fields.Text(
        string='Error Description'
    )

    # Computed fields for better UX
    status_color = fields.Integer(
        string='Status Color',
        compute='_compute_status_color',
        store=False
    )

    @api.depends('status')
    def _compute_status_color(self):
        """Compute color based on status for kanban view"""
        color_map = {
            'new': 4,  # blue
            'processing': 2,  # orange
            'completed_ok': 10,  # green
            'error': 1,  # red
        }
        for record in self:
            record.status_color = color_map.get(record.status, 0)

    def action_set_processing(self):
        """Set task status to processing"""
        self.write({'status': 'processing', 'lastrun': fields.Datetime.now()})

    def action_set_completed(self):
        """Set task status to completed"""
        self.write({
            'status': 'completed_ok',
            'lastrun': fields.Datetime.now(),
            'error_description': False
        })

    def action_set_error(self, error_msg=None):
        """Set task status to error"""
        vals = {
            'status': 'error',
            'lastrun': fields.Datetime.now()
        }
        if error_msg:
            vals['error_description'] = error_msg
        self.write(vals)

    def action_reset_to_new(self):
        """Reset task to new status"""
        self.write({
            'status': 'new',
            'error_description': False
        })