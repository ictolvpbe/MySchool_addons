from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install', 'myschool_account')
class TestAccountDeactivationCascade(TransactionCase):
    """Account-lifecycle: de deactivatie-cascade op myschool.person.

    ``person.write({'is_active': False})`` triggert ``_on_deactivate()`` dat
    de gekoppelde Odoo-user + HR-employee deactiveert en alle proprelaties
    waarin de persoon betrokken is op inactief zet. ``_on_reactivate()``
    herstelt user + employee (proprelaties NIET — die hangen af van sync).
    Daarnaast: proprelation stempelt start_date/end_date bij active-flips.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Person = cls.env['myschool.person']
        cls.PropRelation = cls.env['myschool.proprelation']

    def _make_person_with_account(self, login):
        person = self.Person.create({'name': 'Test, Persoon'})
        user = self.env['res.users'].create({
            'login': login, 'name': 'Test Persoon'})
        employee = self.env['hr.employee'].create({'name': 'Test Persoon'})
        person.write({
            'odoo_user_id': user.id,
            'odoo_employee_id': employee.id,
        })
        return person, user, employee

    def test_deactivate_cascades_to_user_employee_proprelations(self):
        person, user, employee = self._make_person_with_account('acct_deact_1')
        rel = self.PropRelation.create({
            'name': 'rel-1', 'id_person': person.id, 'is_active': True})

        person.write({'is_active': False})

        self.assertFalse(person.is_active)
        self.assertFalse(user.active, 'Odoo-user moet gedeactiveerd zijn')
        self.assertFalse(employee.active, 'HR-employee moet gedeactiveerd zijn')
        self.assertFalse(rel.is_active, 'Proprelatie moet gedeactiveerd zijn')

    def test_reactivate_restores_user_and_employee_not_proprelations(self):
        person, user, employee = self._make_person_with_account('acct_react_1')
        rel = self.PropRelation.create({
            'name': 'rel-2', 'id_person': person.id, 'is_active': True})
        person.write({'is_active': False})
        self.assertFalse(user.active)
        self.assertFalse(rel.is_active)

        person.write({'is_active': True})

        self.assertTrue(person.is_active)
        self.assertTrue(user.active, 'User moet heractiveerd zijn')
        self.assertTrue(employee.active, 'Employee moet heractiveerd zijn')
        self.assertFalse(
            rel.is_active,
            'Proprelaties worden NIET automatisch heractiveerd (sync-afhankelijk)')

    def test_proprelation_stamps_start_and_end_date_on_flip(self):
        rel = self.PropRelation.create({
            'name': 'rel-3', 'is_active': True})
        self.assertTrue(rel.start_date, 'start_date wordt gestempeld bij actieve create')
        self.assertFalse(rel.end_date)

        rel.write({'is_active': False})
        self.assertTrue(rel.end_date, 'end_date wordt gestempeld bij deactivatie')

        rel.write({'is_active': True})
        self.assertFalse(rel.end_date, 'end_date wordt gewist bij heractivatie')
        self.assertTrue(rel.start_date)

    def test_deactivate_handles_person_without_account(self):
        # Geen user/employee gekoppeld → cascade mag niet falen.
        person = self.Person.create({'name': 'Solo, Persoon'})
        person.write({'is_active': False})
        self.assertFalse(person.is_active)


@tagged('post_install', '-at_install', 'myschool_account')
class TestAccountManualPipeline(TransactionCase):
    """Account-lifecycle via de betask-pipeline (MANUAL-pad).

    ``manual.task.service.create_manual_task(obj, action, data)`` maakt een
    MANUAL betask en verwerkt die in immediate-mode synchroon; bij een
    handler-fout volgt een UserError. We testen het IO-vrije pad (geen
    org/PERSON-TREE → geen LDAP/Smartschool-cascade).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Person = cls.env['myschool.person']
        cls.PropRelation = cls.env['myschool.proprelation']
        cls.svc = cls.env['myschool.manual.task.service']
        # Forceer immediate-mode (synchrone verwerking) ongeacht config.
        cls.env['ir.config_parameter'].sudo().set_param(
            'myschool.manual_task_mode', 'immediate')

    def test_manual_person_add_creates_person(self):
        task = self.svc.create_manual_task('PERSON', 'ADD', {
            'first_name': 'Jan', 'last_name': 'Jansen'})
        self.assertEqual(task.status, 'completed_ok')
        person = self.Person.search([('name', '=', 'Jansen, Jan')], limit=1)
        self.assertTrue(person, 'Persoon moet aangemaakt zijn door de pipeline')
        self.assertTrue(person.is_active)
        self.assertEqual(person.first_name, 'Jan')

    def test_manual_person_deact_via_pipeline(self):
        person = self.Person.create({'name': 'Peeters, Piet'})
        user = self.env['res.users'].create({
            'login': 'pipeline_deact', 'name': 'Piet Peeters'})
        person.write({'odoo_user_id': user.id})
        rel = self.PropRelation.create({
            'name': 'rel-deact', 'id_person': person.id, 'is_active': True})

        task = self.svc.create_manual_task('PERSON', 'DEACT', {
            'person_id': person.id})

        self.assertEqual(task.status, 'completed_ok')
        self.assertFalse(person.is_active)
        self.assertFalse(person.automatic_sync,
                         'Manuele deactivatie zet automatic_sync=False')
        self.assertFalse(user.active, 'Cascade deactiveert de Odoo-user')
        self.assertFalse(rel.is_active, 'Cascade deactiveert de proprelaties')

    def test_manual_person_deact_requires_person_id(self):
        # Handler geeft success=False → create_manual_task gooit UserError.
        with self.assertRaises(UserError):
            self.svc.create_manual_task('PERSON', 'DEACT', {})
