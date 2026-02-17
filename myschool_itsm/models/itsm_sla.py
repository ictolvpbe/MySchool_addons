from odoo import models, fields


class ItsmSla(models.Model):
    _name = 'itsm.sla'
    _description = 'ITSM Service Level Agreement'
    _order = 'service_id, priority'

    name = fields.Char(
        string='Name',
        required=True,
    )
    service_id = fields.Many2one(
        'itsm.service',
        string='Service',
        required=True,
        ondelete='cascade',
    )
    ticket_type = fields.Selection(
        [
            ('incident', 'Incident'),
            ('service_request', 'Service Request'),
        ],
        string='Ticket Type',
        required=True,
    )
    priority = fields.Selection(
        [
            ('p1', 'P1 - Critical'),
            ('p2', 'P2 - High'),
            ('p3', 'P3 - Medium'),
            ('p4', 'P4 - Low'),
        ],
        string='Priority',
        required=True,
    )
    response_time_hours = fields.Float(
        string='Response Time (Hours)',
        required=True,
        help='Maximum hours to first response',
    )
    resolution_time_hours = fields.Float(
        string='Resolution Time (Hours)',
        required=True,
        help='Maximum hours to resolution',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
