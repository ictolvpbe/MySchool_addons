from odoo.tests.common import TransactionCase


class TestNascholingsaanvraagBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # --- Users with security groups ---
        group_user = cls.env.ref('nascholingsaanvraag.group_nascholingsaanvraag_user')
        group_directie = cls.env.ref('nascholingsaanvraag.group_nascholingsaanvraag_directie')
        group_boekhouding = cls.env.ref('nascholingsaanvraag.group_nascholingsaanvraag_boekhouding')
        group_vervangingen = cls.env.ref('nascholingsaanvraag.group_nascholingsaanvraag_vervangingen')

        cls.user_employee = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Test Medewerker',
            'login': 'test_medewerker',
            'email': 'medewerker@test.com',
            'group_ids': [(6, 0, [group_user.id])],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Medewerker',
            'user_id': cls.user_employee.id,
        })

        cls.user_directie = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Test Directie',
            'login': 'test_directie',
            'email': 'directie@test.com',
            'group_ids': [(6, 0, [group_directie.id])],
        })
        cls.employee_directie = cls.env['hr.employee'].create({
            'name': 'Test Directie',
            'user_id': cls.user_directie.id,
        })

        cls.user_boekhouding = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Test Boekhouding',
            'login': 'test_boekhouding',
            'email': 'boekhouding@test.com',
            'group_ids': [(6, 0, [group_user.id, group_boekhouding.id])],
        })
        cls.employee_boekhouding = cls.env['hr.employee'].create({
            'name': 'Test Boekhouding',
            'user_id': cls.user_boekhouding.id,
        })

        cls.user_vervangingen = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Test Vervangingen',
            'login': 'test_vervangingen',
            'email': 'vervangingen@test.com',
            'group_ids': [(6, 0, [group_user.id, group_vervangingen.id])],
        })
        cls.employee_vervangingen = cls.env['hr.employee'].create({
            'name': 'Test Vervangingen',
            'user_id': cls.user_vervangingen.id,
        })

        # --- Draft request ---
        cls.request = cls.env['nascholingsaanvraag.record'].with_user(cls.user_employee).create({
            'titel': 'Opleiding Python',
            'description': 'Driedaagse Python-opleiding',
            'employee_id': cls.employee.id,
            'start_date': '2026-04-01',
            'end_date': '2026-04-03',
            'cost': 750.00,
        })
