from odoo import api, fields, models
#from myschool_core.services.informat_service import InformatService

class MySchoolAdminApp(models.Model):
    _name = 'myschool.admin.app'
    _description = 'MySchool Admin Management App'

    name = fields.Char(string='Name')

    def action_trigger_procedure(self):
        """
        Button action to trigger the service procedure
        """
        informat_service = self.env['myschool.InformatService']
        result = informat_service.execute_sync(dev_mode = True)
        return result