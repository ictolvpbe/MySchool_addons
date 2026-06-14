from odoo import fields, models


class MySchoolAdminApp(models.Model):
    _name = 'myschool.admin.app'
    _description = 'MySchool Admin Management App'

    name = fields.Char(string='Name')

    def action_trigger_procedure(self):
        """Placeholder-actie.

        Verwees vroeger naar een Informat-PoC-sync; de Informat-koppeling
        zit nu in de edu-plugin myschool_edu_informat (per-school sync-knop
        op de org-form + de gerichte-sync-wizard). Deze knop doet niets meer.
        """
        return True