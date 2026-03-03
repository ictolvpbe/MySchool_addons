from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TestNascholingsaanvraagBase


@tagged('nascholingsaanvraag', '-at_install', 'post_install')
class TestWorkflow(TestNascholingsaanvraagBase):

    # ------------------------------------------------------------------
    # Full happy path
    # ------------------------------------------------------------------

    def test_full_workflow(self):
        """Draft -> submitted -> approved -> payment + replacement -> done."""
        req = self.request

        self.assertEqual(req.state, 'draft')
        self.assertTrue(req.name.startswith('NA-'))

        # Submit
        req.with_user(self.user_employee).action_submit()
        self.assertEqual(req.state, 'submitted')

        # Approve
        req.with_user(self.user_directie).action_approve()
        self.assertEqual(req.state, 'approved')
        self.assertEqual(req.directie_id, self.employee_directie)

        # Confirm payment (should stay approved, replacement not done yet)
        req.with_user(self.user_boekhouding).action_confirm_payment()
        self.assertTrue(req.payment_done)
        self.assertEqual(req.state, 'approved')

        # Confirm replacement -> triggers done
        req.with_user(self.user_vervangingen).action_confirm_replacement()
        self.assertTrue(req.replacement_done)
        self.assertEqual(req.state, 'done')

    def test_done_replacement_first(self):
        """Replacement confirmed before payment -> stays approved until both done."""
        req = self.request
        req.with_user(self.user_employee).action_submit()
        req.with_user(self.user_directie).action_approve()

        req.with_user(self.user_vervangingen).action_confirm_replacement()
        self.assertEqual(req.state, 'approved')

        req.with_user(self.user_boekhouding).action_confirm_payment()
        self.assertEqual(req.state, 'done')

    # ------------------------------------------------------------------
    # Rejection and reset-to-draft
    # ------------------------------------------------------------------

    def test_reject_and_reset(self):
        """Submitted -> rejected -> reset to draft."""
        req = self.request
        req.with_user(self.user_employee).action_submit()

        req.with_user(self.user_directie).action_reject()
        self.assertEqual(req.state, 'rejected')
        self.assertEqual(req.directie_id, self.employee_directie)

        req.with_user(self.user_employee).action_reset_draft()
        self.assertEqual(req.state, 'draft')
        self.assertFalse(req.directie_id)
        self.assertFalse(req.rejection_reason)

    # ------------------------------------------------------------------
    # Invalid state transitions
    # ------------------------------------------------------------------

    def test_cannot_submit_non_draft(self):
        """Submitting from a non-draft state raises UserError."""
        req = self.request
        req.with_user(self.user_employee).action_submit()
        with self.assertRaises(UserError):
            req.with_user(self.user_employee).action_submit()

    def test_cannot_approve_draft(self):
        """Approving a draft (not submitted) raises UserError."""
        with self.assertRaises(UserError):
            self.request.with_user(self.user_directie).action_approve()

    def test_cannot_reject_draft(self):
        """Rejecting a draft raises UserError."""
        with self.assertRaises(UserError):
            self.request.with_user(self.user_directie).action_reject()

    def test_cannot_confirm_payment_on_draft(self):
        """Confirming payment on a non-approved request raises UserError."""
        with self.assertRaises(UserError):
            self.request.with_user(self.user_boekhouding).action_confirm_payment()

    def test_cannot_confirm_replacement_on_draft(self):
        """Confirming replacement on a non-approved request raises UserError."""
        with self.assertRaises(UserError):
            self.request.with_user(self.user_vervangingen).action_confirm_replacement()

    def test_cannot_reset_non_rejected(self):
        """Resetting a draft (not rejected) raises UserError."""
        with self.assertRaises(UserError):
            self.request.with_user(self.user_employee).action_reset_draft()

    # ------------------------------------------------------------------
    # Sequence generation
    # ------------------------------------------------------------------

    def test_sequence_auto_generated(self):
        """New records get an auto-generated NA-XXXXX reference."""
        self.assertNotEqual(self.request.name, 'New')
        self.assertTrue(self.request.name.startswith('NA-'))
