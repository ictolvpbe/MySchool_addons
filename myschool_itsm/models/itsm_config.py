from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # -- Ticket Defaults from Email --
    itsm_default_ticket_type = fields.Selection(
        [('incident', 'Incident'), ('service_request', 'Service Request')],
        string='Default Ticket Type from Email',
        default='incident',
    )
    itsm_auto_reply = fields.Boolean(
        string='Send Auto-Acknowledgment',
        default=True,
        help='Send an automatic acknowledgment email when a ticket is '
             'created from an incoming email.',
    )
    itsm_alias_name = fields.Char(
        string='Service Desk Email Address',
        help='The email address that receives service desk emails '
             '(e.g. helpdesk@yourschool.be). Odoo will route emails '
             'sent to this address to create new tickets.',
    )

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(
            'myschool_itsm.default_ticket_type',
            self.itsm_default_ticket_type or 'incident',
        )
        ICP.set_param(
            'myschool_itsm.auto_reply',
            str(self.itsm_auto_reply),
        )
        ICP.set_param(
            'myschool_itsm.alias_name',
            self.itsm_alias_name or '',
        )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        res.update(
            itsm_default_ticket_type=ICP.get_param(
                'myschool_itsm.default_ticket_type', 'incident'
            ),
            itsm_auto_reply=ICP.get_param(
                'myschool_itsm.auto_reply', 'True'
            ) == 'True',
            itsm_alias_name=ICP.get_param(
                'myschool_itsm.alias_name', ''
            ),
        )
        return res
