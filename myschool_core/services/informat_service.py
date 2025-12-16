from odoo import api, models


class InformatService:
    def __init__(self, env):
        self.env = env

    def my_procedure(self):
        """
        Your procedure logic here
        """
        # Example: Log something or perform operations
        print("Procedure executed!")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Procedure executed successfully!',
                'type': 'success',
                'sticky': False,
            }
        }