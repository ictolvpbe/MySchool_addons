# -*- coding: utf-8 -*-
"""Tests for Fase A of the AD-takeover refactor.

Covers:
  * environment-consistency validation between session and LDAP config
  * state-machine transitions (approve, resolve_conflict)
  * phase gating (hard block on test, soft warning on prod)
  * STAMP_ID end-to-end with mocked LDAP MODIFY
  * post_init migration of legacy status → new state
"""
import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@contextmanager
def _mock_ldap_connection(modify_result=None):
    """Yield a (mock_conn, ctx_manager) pair.

    ``ctx_manager`` is what should replace ``_get_connection``: an object
    whose ``__enter__`` returns the connection mock. modify_result drives
    ``conn.result`` after the next ``.modify()`` call.
    """
    mock_conn = MagicMock()
    mock_conn.modify.return_value = True
    mock_conn.result = modify_result or {'result': 0, 'description': 'success'}

    class _Ctx:
        def __enter__(self_inner):
            return mock_conn

        def __exit__(self_inner, *exc):
            return False

    yield mock_conn, _Ctx()


@tagged('post_install', '-at_install')
class TestAdTakeoverFaseA(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        OrgType = cls.env['myschool.org.type']
        school_type = OrgType.search([('name', '=', 'SCHOOL')], limit=1) \
            or OrgType.create({'name': 'SCHOOL'})
        cls.school = cls.env['myschool.org'].create({
            'name': 'Test School',
            'name_short': 'ts',
            'inst_nr': '999999',
            'org_type_id': school_type.id,
            'ou_fqdn_internal': 'OU=ts,DC=test,DC=local',
        })
        cls.env.company.school_id = cls.school

        cls.ldap_test = cls.env['myschool.ldap.server.config'].create({
            'name': 'Test LDAP',
            'environment': 'test',
            'server_url': 'ldap://test.local',
            'port': 389,
            'base_dn': 'DC=test,DC=local',
            'bind_dn': 'CN=admin,DC=test,DC=local',
            'bind_password': 'dummy',
            'active': True,
        })
        cls.session = cls.env['myschool.ad.takeover.session'].create({
            'name': 'Fase-A test session',
            'ldap_config_id': cls.ldap_test.id,
            'scope_org_id': cls.school.id,
            'environment': 'test',
        })

    def _make_finding(self, **vals):
        defaults = {
            'session_id': self.session.id,
            'kind': 'user',
            'ad_dn': 'CN=x,OU=ts,DC=test,DC=local',
            'state': 'proposed',
            'source': 'ad',
            'external_id': 'CN=x,OU=ts,DC=test,DC=local',
        }
        defaults.update(vals)
        return self.env['myschool.ad.takeover.finding'].create(defaults)

    def _make_person(self, **vals):
        defaults = {
            'name': 'Doe',
            'first_name': 'John',
            'is_active': True,
        }
        defaults.update(vals)
        return self.env['myschool.person'].create(defaults)

    # ------------------------------------------------------------------
    # Environment-consistency
    # ------------------------------------------------------------------

    def test_env_consistency_validation(self):
        """Assigning a prod-environment to a session bound to a test
        LDAP-config must raise."""
        with self.assertRaises(ValidationError):
            self.session.environment = 'prod'

    def test_env_consistency_accepts_matching_pair(self):
        """Same env on both sides must be accepted (sanity)."""
        prod_cfg = self.env['myschool.ldap.server.config'].create({
            'name': 'Prod LDAP',
            'environment': 'prod',
            'server_url': 'ldap://prod.local',
            'base_dn': 'DC=prod,DC=local',
            'bind_dn': 'CN=admin,DC=prod,DC=local',
            'bind_password': 'dummy',
            'active': True,
        })
        prod_session = self.env['myschool.ad.takeover.session'].create({
            'name': 'Prod session',
            'ldap_config_id': prod_cfg.id,
            'scope_org_id': self.school.id,
            'environment': 'prod',
        })
        self.assertEqual(prod_session.environment, 'prod')

    # ------------------------------------------------------------------
    # State-machine transitions
    # ------------------------------------------------------------------

    def test_approve_requires_proposal_kind(self):
        """action_approve refuses to promote a row without a proposal."""
        f = self._make_finding(proposal_kind=False)
        with self.assertRaises(UserError):
            f.action_approve()
        # state unchanged
        self.assertEqual(f.state, 'proposed')

    def test_approve_promotes_proposed_to_approved(self):
        f = self._make_finding(proposal_kind='link_only')
        f.action_approve()
        self.assertEqual(f.state, 'approved')

    def test_resolve_conflict_marks_ignored(self):
        f = self._make_finding(state='identity_conflict',
                               conflict_reason='test')
        f.action_resolve_conflict()
        self.assertEqual(f.state, 'ignored')
        self.assertEqual(f.proposal_kind, 'ignore')

    def test_resolve_conflict_refuses_non_conflict(self):
        f = self._make_finding(state='proposed', proposal_kind='link_only')
        with self.assertRaises(UserError):
            f.action_resolve_conflict()

    def test_mark_delete_after_refuses_ou(self):
        f = self._make_finding(kind='ou',
                               ad_dn='OU=foo,DC=test,DC=local',
                               external_id='OU=foo,DC=test,DC=local')
        with self.assertRaises(UserError):
            f.action_mark_delete_after()

    # ------------------------------------------------------------------
    # Phase gating
    # ------------------------------------------------------------------

    def test_advance_phase_test_blocks_on_stamp_id_pending(self):
        person = self._make_person(sap_ref='STAMP01')
        self._make_finding(proposal_kind='stamp_id',
                           matched_person_id=person.id)
        with self.assertRaises(UserError):
            self.session.action_advance_phase()
        self.assertEqual(self.session.current_phase, 'preflight')

    def test_advance_phase_test_blocks_on_identity_conflict(self):
        self._make_finding(state='identity_conflict',
                           conflict_reason='test conflict')
        with self.assertRaises(UserError):
            self.session.action_advance_phase()
        self.assertEqual(self.session.current_phase, 'preflight')

    def test_advance_phase_test_clean_succeeds(self):
        """No blockers → phase advances even on test."""
        self.session.action_advance_phase()
        self.assertEqual(self.session.current_phase, 'link')

    def test_advance_phase_prod_soft_warning(self):
        """Prod sessions advance even with pending blockers."""
        prod_cfg = self.env['myschool.ldap.server.config'].create({
            'name': 'Prod LDAP for soft test',
            'environment': 'prod',
            'server_url': 'ldap://prod.local',
            'base_dn': 'DC=prod,DC=local',
            'bind_dn': 'CN=admin,DC=prod,DC=local',
            'bind_password': 'dummy',
            'active': False,    # avoid clashing with another active prod cfg
        })
        prod_session = self.env['myschool.ad.takeover.session'].create({
            'name': 'Prod session soft',
            'ldap_config_id': prod_cfg.id,
            'scope_org_id': self.school.id,
            'environment': 'prod',
        })
        self.env['myschool.ad.takeover.finding'].create({
            'session_id': prod_session.id,
            'kind': 'user',
            'ad_dn': 'CN=y,OU=ts,DC=prod,DC=local',
            'external_id': 'CN=y,OU=ts,DC=prod,DC=local',
            'source': 'ad',
            'state': 'proposed',
            'proposal_kind': 'stamp_id',
        })
        # No exception expected — soft warning only
        prod_session.action_advance_phase()
        self.assertEqual(prod_session.current_phase, 'link')

    # ------------------------------------------------------------------
    # STAMP_ID end-to-end (with mocked LDAP)
    # ------------------------------------------------------------------

    def test_apply_stamp_id_writes_modify(self):
        person = self._make_person(sap_ref='SR12345')
        f = self._make_finding(
            state='approved',
            proposal_kind='stamp_id',
            matched_person_id=person.id,
            proposal_payload_json=json.dumps({
                'target_attribute': 'employeeID',
                'value': 'SR12345',
                'matched_via': 'email_cloud',
            }),
        )
        with _mock_ldap_connection() as (mock_conn, ctx_mgr):
            with patch.object(self.env['myschool.ldap.service'].__class__,
                              '_get_connection',
                              return_value=ctx_mgr):
                f.action_takeover()
        self.assertEqual(f.state, 'done')
        mock_conn.modify.assert_called_once()
        call_args, _ = mock_conn.modify.call_args
        self.assertEqual(call_args[0], f.ad_dn)
        # changes dict — second arg
        changes = call_args[1]
        self.assertIn('employeeID', changes)

    def test_apply_stamp_id_failure_keeps_approved(self):
        """LDAP modify returning a non-zero result leaves the finding
        in state=approved (admin can retry)."""
        person = self._make_person(sap_ref='SR99999')
        f = self._make_finding(
            state='approved',
            proposal_kind='stamp_id',
            matched_person_id=person.id,
            proposal_payload_json=json.dumps({
                'target_attribute': 'employeeID',
                'value': 'SR99999',
                'matched_via': 'email_cloud',
            }),
        )
        with _mock_ldap_connection(
                modify_result={'result': 53, 'description': 'unwilling'}
        ) as (mock_conn, ctx_mgr):
            with patch.object(self.env['myschool.ldap.service'].__class__,
                              '_get_connection',
                              return_value=ctx_mgr):
                with self.assertRaises(UserError):
                    f.action_takeover()
        # state untouched because the apply raised before _mark_done
        self.assertEqual(f.state, 'approved')

    # ------------------------------------------------------------------
    # Legacy migration
    # ------------------------------------------------------------------

    def test_migration_is_idempotent(self):
        """Running the post_init migration twice on existing data must
        leave findings untouched. The NOT-NULL constraints on `state`
        and `source` mean we can't synthesize a pre-migration row in
        the test DB (those constraints exist precisely because the
        first migration ran successfully) — so the test value is
        confirming the WHERE-clauses correctly skip already-migrated
        rows.
        """
        f = self._make_finding(
            kind='ou',
            ad_dn='OU=idem,DC=test,DC=local',
            external_id='OU=idem,DC=test,DC=local',
            state='proposed',
            status='takeover_pending',
            proposal_kind='link_only',
            source='ad',
            risk_level='low',
        )
        before = (f.state, f.proposal_kind, f.source,
                  f.external_id, f.risk_level)

        from odoo.addons.myschool_admin import (
            _migrate_ad_takeover_phase_a_post_init,
        )
        _migrate_ad_takeover_phase_a_post_init(self.env)
        # Run twice — second call must also be a no-op.
        _migrate_ad_takeover_phase_a_post_init(self.env)
        self.env.invalidate_all()

        f2 = self.env['myschool.ad.takeover.finding'].browse(f.id)
        after = (f2.state, f2.proposal_kind, f2.source,
                 f2.external_id, f2.risk_level)
        self.assertEqual(before, after,
            'Migration must not mutate already-migrated rows.')

    def test_legacy_status_migration_mapping_complete(self):
        """Verify the LEGACY_STATUS_MIGRATION table covers every
        legacy status value defined in STATUS_SELECTION. If a new
        legacy status is added later without an entry here, this
        test catches it before deploy."""
        from odoo.addons.myschool_admin.models.ad_takeover import (
            STATUS_SELECTION, LEGACY_STATUS_MIGRATION,
        )
        legacy_status_keys = {key for key, _label in STATUS_SELECTION}
        migration_keys = set(LEGACY_STATUS_MIGRATION.keys())
        self.assertEqual(legacy_status_keys, migration_keys,
            f'Mismatch between STATUS_SELECTION and LEGACY_STATUS_'
            f'MIGRATION. Missing in mapping: '
            f'{legacy_status_keys - migration_keys}. '
            f'Extra in mapping: {migration_keys - legacy_status_keys}.')

        # Every mapping value must map to a valid STATE_SELECTION key.
        from odoo.addons.myschool_admin.models.ad_takeover import (
            STATE_SELECTION, PROPOSAL_KIND_SELECTION,
        )
        valid_states = {key for key, _label in STATE_SELECTION}
        valid_kinds = {key for key, _label in PROPOSAL_KIND_SELECTION}
        for legacy, (new_state, new_kind) in LEGACY_STATUS_MIGRATION.items():
            self.assertIn(new_state, valid_states,
                f'{legacy} maps to unknown state {new_state}')
            if new_kind is not None:
                self.assertIn(new_kind, valid_kinds,
                    f'{legacy} maps to unknown proposal_kind {new_kind}')
