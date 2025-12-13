from odoo import models, fields

class CiRelation(models.Model):
    _name = 'myschool.ci.relation'
    _description = 'Myschool CI Relation'

    name = fields.Char(string="Name")
    isactive = fields.Boolean(string="is active", default=True, required=False)

    id_ci = fields.Many2one(
        comodel_name="myschool.config.item",
        string="Config Item",
        ondelete="set null",
    )

    id_role = fields.Many2one(
        comodel_name="myschool.role",    # AANPASSEN: jouw Role-model
        string="Role",
        ondelete="set null",
    )

    id_org = fields.Many2one(
        comodel_name="myschool.org",     # AANPASSEN: jouw Org-model
        string="Org",
        ondelete="set null",
    )

    id_person = fields.Many2one(
        comodel_name="myschool.person",  # AANPASSEN
        string="Person",
        ondelete="set null",
    )

    id_period = fields.Many2one(
        comodel_name="myschool.period",  # AANPASSEN
        string="Period",
        ondelete="set null",
    )

    # id_sysmodule = fields.Many2one(
    #     comodel_name="res.sysmodule",  # AANPASSEN
    #     string="System Module",
    #     ondelete="set null",
    # )

