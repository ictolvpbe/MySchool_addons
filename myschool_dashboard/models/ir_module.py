from odoo import models


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def button_immediate_upgrade(self):
        super().button_immediate_upgrade()
        return {
            'type': 'ir.actions.act_url',
            'url': '/odoo/apps',
            'target': 'self',
        }
