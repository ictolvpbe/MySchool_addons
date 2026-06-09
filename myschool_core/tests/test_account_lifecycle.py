from unittest.mock import patch

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


@tagged('post_install', '-at_install', 'myschool_account')
class TestPersonTreePosition(TransactionCase):
    """Account-lifecycle: PERSON-TREE-plaatsing via PPSBR.

    ``_update_person_tree_position`` kiest uit de actieve PPSBR-relaties de
    rol met hoogste prioriteit (laagste nummer; ``is_master`` overschrijft)
    en zet één PERSON-TREE naar de target-org (zonder BRSO = de PPSBR-org).
    De FQDN/email-stap (``_populate_person_account_fields``) wordt gepatcht
    zodat we puur de plaatsing toetsen.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Person = cls.env['myschool.person']
        cls.Org = cls.env['myschool.org']
        cls.Role = cls.env['myschool.role']
        cls.Rel = cls.env['myschool.proprelation']
        cls.RelType = cls.env['myschool.proprelation.type']
        cls.processor = cls.env['myschool.betask.processor']
        # PPSBR-type is niet geseed → zelf aanmaken (PERSON-TREE maakt de
        # methode zelf aan als die ontbreekt).
        cls.ppsbr_type = cls.RelType.search([('name', '=', 'PPSBR')], limit=1) \
            or cls.RelType.create({'name': 'PPSBR'})
        cls.org_a = cls._make_org('Org A', '1000000001')
        cls.org_b = cls._make_org('Org B', '1000000002')
        cls.role_high = cls.Role.create({'name': 'ROLE_HIGH', 'priority': 1})
        cls.role_low = cls.Role.create({'name': 'ROLE_LOW', 'priority': 5})

    @classmethod
    def _make_org(cls, name, inst_nr):
        return cls.Org.create({
            'name': name, 'name_short': name, 'inst_nr': inst_nr})

    def _ppsbr(self, person, role, org, is_master=False):
        return self.Rel.create({
            'name': f'PPSBR-{person.id}-{role.id}',
            'proprelation_type_id': self.ppsbr_type.id,
            'id_person': person.id, 'id_role': role.id, 'id_org': org.id,
            'is_active': True, 'is_master': is_master,
        })

    def _person_tree(self, person):
        return self.Rel.search([
            ('id_person', '=', person.id),
            ('proprelation_type_id.name', '=', 'PERSON-TREE'),
            ('is_active', '=', True),
        ])

    def _run(self, person):
        # Patch de FQDN/email-stap weg — die hangt af van LDAP-templates.
        with patch.object(type(self.processor),
                          '_populate_person_account_fields', return_value=None):
            self.processor._update_person_tree_position(person)

    def test_tree_created_from_single_ppsbr(self):
        person = self.Person.create({'name': 'Tree, Een'})
        self._ppsbr(person, self.role_high, self.org_a)
        self._run(person)
        tree = self._person_tree(person)
        self.assertEqual(len(tree), 1, 'Eén PERSON-TREE verwacht')
        self.assertEqual(tree.id_org, self.org_a)
        self.assertEqual(tree.id_role, self.role_high)

    def test_tree_picks_highest_priority_role(self):
        person = self.Person.create({'name': 'Tree, Twee'})
        self._ppsbr(person, self.role_low, self.org_b)    # priority 5
        self._ppsbr(person, self.role_high, self.org_a)   # priority 1 (wint)
        self._run(person)
        tree = self._person_tree(person)
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree.id_org, self.org_a, 'Hoogste prioriteit (1) wint')
        self.assertEqual(tree.id_role, self.role_high)

    def test_master_ppsbr_overrides_priority(self):
        person = self.Person.create({'name': 'Tree, Drie'})
        self._ppsbr(person, self.role_high, self.org_a)             # priority 1
        self._ppsbr(person, self.role_low, self.org_b, is_master=True)  # master wint
        self._run(person)
        tree = self._person_tree(person)
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree.id_org, self.org_b, 'is_master overschrijft prioriteit')
        self.assertEqual(tree.id_role, self.role_low)

    def test_tree_deactivated_when_no_active_ppsbr(self):
        person = self.Person.create({'name': 'Tree, Vier'})
        ppsbr = self._ppsbr(person, self.role_high, self.org_a)
        self._run(person)
        self.assertEqual(len(self._person_tree(person)), 1)
        # Verwijder de enige PPSBR → herberekening deactiveert de PERSON-TREE.
        ppsbr.write({'is_active': False})
        self._run(person)
        self.assertEqual(len(self._person_tree(person)), 0,
                         'Zonder actieve PPSBR mag er geen PERSON-TREE blijven')
