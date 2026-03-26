from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestActiviteiten(TransactionCase):
    """Tests for the activiteiten module: workflow, constraints, and business logic."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create a school (myschool.org)
        cls.school = cls.env['myschool.org'].create({
            'name': 'Test School',
            'name_short': 'TS',
            'inst_nr': '999999',
        })

        # Link school to company
        cls.env.company.school_id = cls.school

        # Create admin user with full access
        cls.admin_group = cls.env.ref('activiteiten.group_activiteiten_admin')
        cls.user_admin = cls.env['res.users'].create({
            'name': 'Act Admin',
            'login': 'act_admin',
            'group_ids': [(4, cls.admin_group.id)],
        })

        # Create directie user
        cls.directie_group = cls.env.ref('activiteiten.group_activiteiten_directie')
        cls.user_directie = cls.env['res.users'].create({
            'name': 'Act Directie',
            'login': 'act_directie',
            'group_ids': [(4, cls.directie_group.id)],
        })

        # Create aankoop user
        cls.aankoop_group = cls.env.ref('activiteiten.group_activiteiten_aankoop')
        cls.user_aankoop = cls.env['res.users'].create({
            'name': 'Act Aankoop',
            'login': 'act_aankoop',
            'group_ids': [(4, cls.aankoop_group.id)],
        })

        # Create boekhouding user
        cls.boekhouding_group = cls.env.ref('activiteiten.group_activiteiten_boekhouding')
        cls.user_boekhouding = cls.env['res.users'].create({
            'name': 'Act Boekhouding',
            'login': 'act_boekhouding',
            'group_ids': [(4, cls.boekhouding_group.id)],
        })

        # Create personeelslid user
        cls.personeelslid_group = cls.env.ref('activiteiten.group_activiteiten_personeelslid')
        cls.user_personnel = cls.env['res.users'].create({
            'name': 'Act Personeelslid',
            'login': 'act_personnel',
            'group_ids': [(4, cls.personeelslid_group.id)],
        })

        # Future datetimes for tests
        cls.future_start = fields.Datetime.now() + timedelta(days=30)
        cls.future_end = fields.Datetime.now() + timedelta(days=30, hours=4)
        cls.future_end_multiday = fields.Datetime.now() + timedelta(days=32)

    def _create_activity(self, user=None, **kwargs):
        """Helper to create an activity with sensible defaults."""
        vals = {
            'titel': 'Test Activiteit',
            'activity_type': 'buitenschools',
            'school_id': self.school.id,
            'datetime': self.future_start,
            'datetime_end': self.future_end,
        }
        vals.update(kwargs)
        env = self.env
        if user:
            env = self.env(user=user)
        return env['activiteiten.record'].create(vals)

    # =========================================================================
    # 1. CREATION TESTS
    # =========================================================================

    def test_create_activity_generates_reference(self):
        """New activity should get an auto-generated ACT-XXXXX reference."""
        act = self._create_activity(user=self.user_admin)
        self.assertTrue(act.name.startswith('ACT-'))

    def test_create_activity_sets_state_form_invullen(self):
        """When activity_type is set at creation, state should be 'form_invullen'."""
        act = self._create_activity(user=self.user_admin)
        self.assertEqual(act.state, 'form_invullen')

    def test_create_activity_draft_without_type(self):
        """Activity without activity_type should stay in 'draft'."""
        act = self.env['activiteiten.record'].create({
            'titel': 'Draft Test',
        })
        self.assertEqual(act.state, 'draft')

    def test_create_unique_references(self):
        """Each activity should get a unique reference."""
        act1 = self._create_activity(user=self.user_admin)
        act2 = self._create_activity(user=self.user_admin)
        self.assertNotEqual(act1.name, act2.name)

    # =========================================================================
    # 2. CONSTRAINT TESTS
    # =========================================================================

    def test_constraint_start_date_in_past(self):
        """Cannot create activity with start date in the past."""
        with self.assertRaises(UserError):
            self._create_activity(
                user=self.user_admin,
                datetime=fields.Datetime.now() - timedelta(days=1),
            )

    def test_constraint_end_before_start(self):
        """End date must be after start date."""
        with self.assertRaises(UserError):
            self._create_activity(
                user=self.user_admin,
                datetime=self.future_start,
                datetime_end=self.future_start - timedelta(hours=1),
            )

    # =========================================================================
    # 3. WORKFLOW TESTS - SUBMIT
    # =========================================================================

    def test_submit_without_title_raises(self):
        """Cannot submit without a title."""
        act = self._create_activity(user=self.user_admin, titel=False)
        with self.assertRaises(UserError):
            act.action_submit_form()

    def test_submit_without_datetime_raises(self):
        """Cannot submit without a start date."""
        act = self._create_activity(user=self.user_admin, datetime=False, datetime_end=False)
        with self.assertRaises(UserError):
            act.action_submit_form()

    def test_submit_no_bus_goes_to_pending(self):
        """Submit without bus → pending_approval."""
        act = self._create_activity(user=self.user_admin, bus_nodig=False)
        act.action_submit_form()
        self.assertEqual(act.state, 'pending_approval')

    def test_submit_with_bus_goes_to_bus_check(self):
        """Submit with bus needed → bus_check."""
        act = self._create_activity(user=self.user_admin, bus_nodig=True)
        act.action_submit_form()
        self.assertEqual(act.state, 'bus_check')

    def test_submit_from_wrong_state_raises(self):
        """Cannot submit from pending_approval state."""
        act = self._create_activity(user=self.user_admin)
        act.action_submit_form()  # → pending_approval
        with self.assertRaises(UserError):
            act.action_submit_form()

    # =========================================================================
    # 4. WORKFLOW TESTS - BUS CHECK
    # =========================================================================

    def test_bus_approved_goes_to_pending(self):
        """Bus approved → pending_approval."""
        act = self._create_activity(user=self.user_admin, bus_nodig=True)
        act.action_submit_form()
        self.assertEqual(act.state, 'bus_check')
        act.action_bus_approved()
        self.assertEqual(act.state, 'pending_approval')
        self.assertTrue(act.bus_available)

    def test_bus_refused_goes_to_bus_refused(self):
        """Bus refused → bus_refused."""
        act = self._create_activity(user=self.user_admin, bus_nodig=True)
        act.action_submit_form()
        act.action_bus_refused()
        self.assertEqual(act.state, 'bus_refused')
        self.assertFalse(act.bus_available)

    def test_bus_approved_wrong_state_raises(self):
        """Cannot approve bus from wrong state."""
        act = self._create_activity(user=self.user_admin)
        with self.assertRaises(UserError):
            act.action_bus_approved()

    def test_bus_refused_resubmit(self):
        """After bus refused, can reset and resubmit."""
        act = self._create_activity(user=self.user_admin, bus_nodig=True)
        act.action_submit_form()
        act.action_bus_refused()
        self.assertEqual(act.state, 'bus_refused')
        act.action_reset_to_form()
        self.assertEqual(act.state, 'form_invullen')

    # =========================================================================
    # 5. WORKFLOW TESTS - APPROVAL
    # =========================================================================

    def test_approve_goes_to_s_code(self):
        """Approve → s_code."""
        act = self._create_activity(user=self.user_admin)
        act.action_submit_form()
        act.action_approve()
        self.assertEqual(act.state, 's_code')

    def test_reject_without_reason_raises(self):
        """Cannot reject without a reason."""
        act = self._create_activity(user=self.user_admin)
        act.action_submit_form()
        with self.assertRaises(UserError):
            act.action_reject()

    def test_reject_with_reason(self):
        """Reject with reason → rejected."""
        act = self._create_activity(user=self.user_admin)
        act.action_submit_form()
        act.rejection_reason = 'Te duur'
        act.action_reject()
        self.assertEqual(act.state, 'rejected')

    def test_approve_wrong_state_raises(self):
        """Cannot approve from wrong state."""
        act = self._create_activity(user=self.user_admin)
        with self.assertRaises(UserError):
            act.action_approve()

    def test_reject_wrong_state_raises(self):
        """Cannot reject from wrong state."""
        act = self._create_activity(user=self.user_admin)
        with self.assertRaises(UserError):
            act.action_reject()

    def test_rejected_can_reset(self):
        """Rejected activity can be reset to form_invullen."""
        act = self._create_activity(user=self.user_admin)
        act.action_submit_form()
        act.rejection_reason = 'Reden'
        act.action_reject()
        act.action_reset_to_form()
        self.assertEqual(act.state, 'form_invullen')

    def test_reset_from_wrong_state_raises(self):
        """Cannot reset from pending_approval."""
        act = self._create_activity(user=self.user_admin)
        act.action_submit_form()
        with self.assertRaises(UserError):
            act.action_reset_to_form()

    # =========================================================================
    # 6. WORKFLOW TESTS - S-CODE & DONE
    # =========================================================================

    def test_confirm_s_code_without_name_raises(self):
        """Cannot confirm S-Code without s_code_name."""
        act = self._create_activity(user=self.user_admin)
        act.action_submit_form()
        act.action_approve()
        with self.assertRaises(UserError):
            act.action_confirm_s_code()

    def test_confirm_s_code_completes(self):
        """Confirm S-Code with name → done."""
        act = self._create_activity(user=self.user_admin)
        act.action_submit_form()
        act.action_approve()
        act.s_code_name = 'S-12345'
        act.action_confirm_s_code()
        self.assertEqual(act.state, 'done')

    def test_confirm_s_code_wrong_state_raises(self):
        """Cannot confirm S-Code from wrong state."""
        act = self._create_activity(user=self.user_admin)
        with self.assertRaises(UserError):
            act.action_confirm_s_code()

    # =========================================================================
    # 7. FULL WORKFLOW TEST
    # =========================================================================

    def test_full_workflow_no_bus(self):
        """Complete workflow without bus: create → submit → approve → s_code → done."""
        act = self._create_activity(user=self.user_admin)
        self.assertEqual(act.state, 'form_invullen')

        act.action_submit_form()
        self.assertEqual(act.state, 'pending_approval')

        act.action_approve()
        self.assertEqual(act.state, 's_code')

        act.s_code_name = 'S-99999'
        act.action_confirm_s_code()
        self.assertEqual(act.state, 'done')

    def test_full_workflow_with_bus(self):
        """Complete workflow with bus: create → submit → bus_check → approve → s_code → done."""
        act = self._create_activity(user=self.user_admin, bus_nodig=True, bus_price=150.0)
        self.assertEqual(act.state, 'form_invullen')

        act.action_submit_form()
        self.assertEqual(act.state, 'bus_check')

        act.action_bus_approved()
        self.assertEqual(act.state, 'pending_approval')

        act.action_approve()
        self.assertEqual(act.state, 's_code')

        act.s_code_name = 'S-88888'
        act.action_confirm_s_code()
        self.assertEqual(act.state, 'done')

    # =========================================================================
    # 8. COST LINE TESTS
    # =========================================================================

    def test_cost_line_creation(self):
        """Can add cost lines to an activity."""
        act = self._create_activity(user=self.user_admin)
        self.env['activiteiten.kosten.line'].create({
            'activiteit_id': act.id,
            'omschrijving': 'Entree',
            'bedrag': 15.0,
            'kosten_type': 'vast',
        })
        self.assertEqual(act.totale_kost, 15.0)

    def test_auto_cost_lines_on_confirm(self):
        """S-Code confirmation creates auto cost lines (bus)."""
        act = self._create_activity(user=self.user_admin, bus_nodig=True, bus_price=200.0)
        act.action_submit_form()
        act.action_bus_approved()
        act.action_approve()
        act.s_code_name = 'S-77777'
        act.action_confirm_s_code()
        bus_lines = act.kosten_ids.filtered(lambda l: l.is_auto and l.omschrijving == 'Bus')
        self.assertTrue(bus_lines)
        self.assertEqual(bus_lines[0].bedrag, 200.0)

    def test_cannot_delete_auto_cost_lines(self):
        """Auto cost lines cannot be deleted manually."""
        act = self._create_activity(user=self.user_admin, bus_nodig=True, bus_price=100.0)
        act.action_submit_form()
        act.action_bus_approved()
        act.action_approve()
        act.s_code_name = 'S-66666'
        act.action_confirm_s_code()
        auto_lines = act.kosten_ids.filtered(lambda l: l.is_auto)
        if auto_lines:
            with self.assertRaises(UserError):
                auto_lines[0].unlink()

    def test_multiday_insurance_calculation(self):
        """Multi-day activities should get insurance auto-line on confirm."""
        act = self._create_activity(
            user=self.user_admin,
            datetime=self.future_start,
            datetime_end=self.future_end_multiday,  # 2 days later
        )
        # Add a manual cost
        self.env['activiteiten.kosten.line'].create({
            'activiteit_id': act.id,
            'omschrijving': 'Verblijf',
            'bedrag': 100.0,
            'kosten_type': 'vast',
        })
        act.action_submit_form()
        act.action_approve()
        act.s_code_name = 'S-55555'
        act.action_confirm_s_code()
        insurance_lines = act.kosten_ids.filtered(
            lambda l: l.is_auto and 'Verzekering' in (l.omschrijving or ''))
        self.assertTrue(insurance_lines, "Multi-day activity should have insurance line")
        self.assertTrue(act.verzekering_done)

    def test_singleday_no_insurance(self):
        """Single-day activities should NOT get insurance."""
        act = self._create_activity(
            user=self.user_admin,
            datetime=self.future_start,
            datetime_end=self.future_end,  # Same day
        )
        act.action_submit_form()
        act.action_approve()
        act.s_code_name = 'S-44444'
        act.action_confirm_s_code()
        insurance_lines = act.kosten_ids.filtered(
            lambda l: l.is_auto and 'Verzekering' in (l.omschrijving or ''))
        self.assertFalse(insurance_lines, "Single-day activity should NOT have insurance")
        self.assertFalse(act.verzekering_done)

    # =========================================================================
    # 9. DELETE RESTRICTIONS
    # =========================================================================

    def test_delete_draft_allowed(self):
        """Can delete activity in draft/form_invullen state."""
        act = self._create_activity(user=self.user_admin)
        act_id = act.id
        act.unlink()
        self.assertFalse(self.env['activiteiten.record'].browse(act_id).exists())

    def test_delete_submitted_by_non_admin_raises(self):
        """Non-admin cannot delete submitted activity."""
        act = self._create_activity(user=self.user_personnel)
        act.action_submit_form()
        with self.assertRaises(UserError):
            act.with_user(self.user_personnel).unlink()

    # =========================================================================
    # 10. COMPUTED FIELDS
    # =========================================================================

    def test_display_name_with_title(self):
        """Display name should include reference and title."""
        act = self._create_activity(user=self.user_admin, titel='Schoolreis Gent')
        self.assertIn('Schoolreis Gent', act.display_name)
        self.assertIn('ACT-', act.display_name)

    def test_is_owner_computed(self):
        """is_owner should be True for creator."""
        act = self._create_activity(user=self.user_admin)
        self.assertTrue(act.with_user(self.user_admin).is_owner)
        self.assertFalse(act.with_user(self.user_directie).is_owner)

    def test_totale_kost_computed(self):
        """Total cost should sum all cost lines."""
        act = self._create_activity(user=self.user_admin)
        self.env['activiteiten.kosten.line'].create([
            {'activiteit_id': act.id, 'omschrijving': 'Item 1', 'bedrag': 10.0, 'kosten_type': 'vast'},
            {'activiteit_id': act.id, 'omschrijving': 'Item 2', 'bedrag': 25.0, 'kosten_type': 'variabel'},
        ])
        act.invalidate_recordset()
        self.assertEqual(act.totale_kost, 35.0)
