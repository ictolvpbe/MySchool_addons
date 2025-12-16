from odoo import api, fields, models
from ..services.informat_service import InformatService


class MySchoolCoreApp(models.Model):
    _name = 'myschool.core.app'
    _description = 'MySchool Core Management App'

    name = fields.Char(string='Name')

    def action_trigger_procedure(self):
        """
        Button action to trigger the service procedure
        """
        service = InformatService(self.env)
        result = service.my_procedure()
        return result