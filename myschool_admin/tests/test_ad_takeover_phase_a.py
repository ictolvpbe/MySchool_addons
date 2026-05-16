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
from contextlib import contextmanager, ExitStack
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@contextmanager
def _mock_ldap_connection(modify_result=None, search_entries=None):
    """Yield a (mock_conn, ctx_manager) pair.

    ``ctx_manager`` is what should replace ``_get_connection``: an object
    whose ``__enter__`` returns the connection mock. modify_result drives
    ``conn.result`` after the next ``.modify()`` / ``.modify_dn()`` call.
    ``search_entries`` populates ``conn.entries`` for snapshot reads.
    """
    mock_conn = MagicMock()
    mock_conn.modify.return_value = True
    mock_conn.modify_dn.return_value = True
    mock_conn.result = modify_result or {'result': 0, 'description': 'success'}
    mock_conn.entries = search_entries or []

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

    # ------------------------------------------------------------------
    # Fase B — Cloud scanner (mocked fetch helpers)
    # ------------------------------------------------------------------

    def _make_cloud_session(self):
        """Create a session with a Google config but no LDAP, so the
        Cloud scanner runs in isolation. Mocks the fetch-helpers
        in-place on the session record.
        """
        gcfg = self.env['myschool.google.workspace.config'].create({
            'name': 'Test Google',
            'environment': 'test',
            'domain': 'test.olvp.lab',
            'subject_email': 'admin@test.olvp.lab',
            'customer_id': 'my_customer',
            'active': False,
        })
        session = self.env['myschool.ad.takeover.session'].create({
            'name': 'Cloud-only session',
            'google_workspace_config_id': gcfg.id,
            'scope_org_id': self.school.id,
            'environment': 'test',
        })
        return session

    def _patch_cloud_fetchers(self, session, ous=None, users=None,
                              groups=None):
        """Return a list of patches the test wraps in an ExitStack /
        nested with-blocks. Patches the fetch-helpers and the Google
        availability/connection probes."""
        session_cls = type(session)
        gsvc = self.env['myschool.google.directory.service']
        return [
            patch.object(session_cls, '_cloud_fetch_ous',
                         return_value=list(ous or [])),
            patch.object(session_cls, '_cloud_fetch_users',
                         return_value=list(users or [])),
            patch.object(session_cls, '_cloud_fetch_groups',
                         return_value=list(groups or [])),
            patch.object(type(gsvc), '_check_google_available',
                         return_value=True),
            patch.object(type(gsvc), '_get_directory_service',
                         return_value=object()),
        ]

    def test_at_least_one_source_required(self):
        with self.assertRaises(ValidationError):
            self.env['myschool.ad.takeover.session'].create({
                'name': 'No-source session',
                'scope_org_id': self.school.id,
                'environment': 'test',
            })

    def test_cloud_scan_orphan_user(self):
        session = self._make_cloud_session()
        patches = self._patch_cloud_fetchers(session, users=[{
            'id': 'cloud-uid-orphan-1',
            'primaryEmail': 'unknown@test.olvp.lab',
            'name': {'givenName': 'Test', 'familyName': 'Orphan',
                     'fullName': 'Test Orphan'},
        }])
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            session.action_scan()
        finding = session.finding_ids.filtered(lambda f: f.kind == 'user')
        self.assertEqual(len(finding), 1)
        self.assertEqual(finding.source, 'cloud')
        self.assertEqual(finding.state, 'proposed')
        self.assertEqual(finding.proposal_kind, 'link_only')
        self.assertEqual(finding.risk_level, 'medium')

    def test_cloud_scan_sap_ref_match_done(self):
        person = self._make_person(
            sap_ref='CLOUD01', email_cloud='match@test.olvp.lab')
        session = self._make_cloud_session()
        patches = self._patch_cloud_fetchers(session, users=[{
            'id': 'cloud-uid-match-1',
            'primaryEmail': 'match@test.olvp.lab',
            'name': {'givenName': 'Test', 'familyName': 'Match'},
            'externalIds': [{'type': 'organization', 'value': 'CLOUD01'}],
        }])
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            session.action_scan()
        finding = session.finding_ids.filtered(lambda f: f.kind == 'user')
        self.assertEqual(finding.state, 'done')
        self.assertEqual(finding.matched_person_id, person)

    def test_cloud_scan_stamp_id_via_email(self):
        person = self._make_person(
            sap_ref='CLOUD02', email_cloud='via@test.olvp.lab')
        session = self._make_cloud_session()
        patches = self._patch_cloud_fetchers(session, users=[{
            'id': 'cloud-uid-stamp-1',
            'primaryEmail': 'via@test.olvp.lab',
            'name': {'givenName': 'Test', 'familyName': 'Stamp'},
        }])
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            session.action_scan()
        finding = session.finding_ids.filtered(lambda f: f.kind == 'user')
        self.assertEqual(finding.state, 'proposed')
        self.assertEqual(finding.proposal_kind, 'stamp_id')
        self.assertEqual(finding.matched_person_id, person)
        payload = json.loads(finding.proposal_payload_json or '{}')
        self.assertEqual(payload.get('target_attribute'), 'externalIds')
        self.assertEqual(payload.get('value'), 'CLOUD02')

    def test_cloud_scan_identity_conflict_email_mismatch(self):
        """Same sap_ref in Cloud as a DB-person, but the Cloud user's
        primaryEmail disagrees with DB.person.email_cloud → conflict."""
        person = self._make_person(
            sap_ref='CLOUD03', email_cloud='canonical@test.olvp.lab')
        session = self._make_cloud_session()
        patches = self._patch_cloud_fetchers(session, users=[{
            'id': 'cloud-uid-conflict-1',
            'primaryEmail': 'drifted@test.olvp.lab',
            'name': {'givenName': 'Test', 'familyName': 'Conflict'},
            'externalIds': [{'type': 'organization', 'value': 'CLOUD03'}],
        }])
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            session.action_scan()
        finding = session.finding_ids.filtered(lambda f: f.kind == 'user')
        self.assertEqual(finding.state, 'identity_conflict')
        self.assertEqual(finding.matched_person_id, person)
        self.assertIn('drifted', finding.conflict_reason or '')

    # ------------------------------------------------------------------
    # Fase B — Cross-source linker
    # ------------------------------------------------------------------

    def test_cross_source_siblings_populated(self):
        """Same sap_ref appears in AD and Cloud → both findings list
        each other in sibling_ids after the scan completes."""
        person = self._make_person(
            sap_ref='XR01', email_cloud='xr01@test.olvp.lab')
        # Use a session with BOTH ldap and google configured.
        gcfg = self.env['myschool.google.workspace.config'].create({
            'name': 'XR Google',
            'environment': 'test',
            'domain': 'test.olvp.lab',
            'subject_email': 'admin@test.olvp.lab',
            'customer_id': 'my_customer',
            'active': False,
        })
        session = self.env['myschool.ad.takeover.session'].create({
            'name': 'Cross-source session',
            'ldap_config_id': self.ldap_test.id,
            'google_workspace_config_id': gcfg.id,
            'scope_org_id': self.school.id,
            'environment': 'test',
        })

        ad_stub_payload = ([{
            'session_id': session.id,
            'source': 'ad',
            'external_id': 'CN=jan,OU=ts,DC=test,DC=local',
            'kind': 'user',
            'ad_dn': 'CN=jan,OU=ts,DC=test,DC=local',
            'ad_cn': 'jan',
            'ad_mail': 'xr01@test.olvp.lab',
            'sap_ref': 'XR01',
            'state': 'done',
            'status': 'matched',
            'matched_person_id': person.id,
            'risk_level': 'low',
            'match_kind': 'matched_in_db',
        }], 'AD-stub')
        patches = self._patch_cloud_fetchers(session, users=[{
            'id': 'cloud-jan',
            'primaryEmail': 'xr01@test.olvp.lab',
            'name': {'givenName': 'Jan', 'familyName': 'Test'},
            'externalIds': [{'type': 'organization', 'value': 'XR01'}],
        }])
        patches.append(patch.object(
            type(session), '_scan_ad', return_value=ad_stub_payload))
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            session.action_scan()

        users = session.finding_ids.filtered(lambda f: f.kind == 'user')
        self.assertEqual(len(users), 2)
        ad_finding = users.filtered(lambda f: f.source == 'ad')
        cloud_finding = users.filtered(lambda f: f.source == 'cloud')
        self.assertEqual(ad_finding.sibling_ids, cloud_finding)
        self.assertEqual(cloud_finding.sibling_ids, ad_finding)

    def test_cross_source_drift_marks_conflict(self):
        """AD-finding and Cloud-finding both claim sap_ref=XR99 but each
        points at a different DB-person → cross-source linker promotes
        both to state=identity_conflict.

        sap_ref carries a UNIQUE constraint on person, so we can't have
        two DB-persons with the same sap_ref. Instead we test the
        drift-detection logic directly by inserting two finding-stubs
        with different matched_person_id but identical sap_ref —
        which simulates the real-world "AD says X belongs to person A,
        Cloud says X belongs to person B" data corruption.
        """
        person_a = self._make_person(
            sap_ref='XR99', email_cloud='a@test.olvp.lab')
        person_b = self._make_person(
            name='Other', email_cloud='b@test.olvp.lab')
        gcfg = self.env['myschool.google.workspace.config'].create({
            'name': 'Drift Google',
            'environment': 'test',
            'domain': 'test.olvp.lab',
            'subject_email': 'admin@test.olvp.lab',
            'customer_id': 'my_customer',
            'active': False,
        })
        session = self.env['myschool.ad.takeover.session'].create({
            'name': 'Drift session',
            'ldap_config_id': self.ldap_test.id,
            'google_workspace_config_id': gcfg.id,
            'scope_org_id': self.school.id,
            'environment': 'test',
        })
        # Create two stub findings directly — simulating the post-scan
        # state where both bronnen agreed on sap_ref but disagreed
        # on matched_person_id.
        Finding = self.env['myschool.ad.takeover.finding']
        Finding.create([{
            'session_id': session.id,
            'source': 'ad',
            'external_id': 'CN=a,OU=ts,DC=test,DC=local',
            'kind': 'user',
            'ad_dn': 'CN=a,OU=ts,DC=test,DC=local',
            'ad_cn': 'a',
            'sap_ref': 'XR99',
            'state': 'done',
            'matched_person_id': person_a.id,
        }, {
            'session_id': session.id,
            'source': 'cloud',
            'external_id': 'cloud-drift',
            'kind': 'user',
            'ad_dn': 'b@test.olvp.lab',
            'ad_cn': 'b',
            'sap_ref': 'XR99',
            'state': 'done',
            'matched_person_id': person_b.id,
        }])
        # Run the linker directly — it's the unit under test
        siblings, drift = session._link_cross_source()
        self.assertEqual(siblings, 2)
        self.assertEqual(drift, 2)

        users = session.finding_ids.filtered(lambda f: f.kind == 'user')
        self.assertEqual(len(users), 2)
        for f in users:
            self.assertEqual(f.state, 'identity_conflict')
            self.assertIn('Cross-source', f.conflict_reason or '')

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

    # ------------------------------------------------------------------
    # Fase C — pilot / verify / rollback
    # ------------------------------------------------------------------

    def _ldap_entry_with(self, **attrs):
        """Build a mock ldap3-entry whose attribute access returns a
        thing-with-a-``.value``."""
        entry = MagicMock()
        for key, val in attrs.items():
            attr = MagicMock()
            attr.value = val
            setattr(entry, key, attr)
            entry.__getitem__.side_effect = (
                lambda k, _attrs=attrs: MagicMock(value=_attrs.get(k, '')))
        return entry

    def test_pilot_captures_snapshot_and_applies(self):
        """STAMP_ID pilot: state goes approved → applied_pilot, snapshot
        is persisted, AND the LDAP MODIFY ran."""
        person = self._make_person(sap_ref='PILOT01')
        f = self._make_finding(
            state='approved',
            proposal_kind='stamp_id',
            matched_person_id=person.id,
            proposal_payload_json=json.dumps({
                'target_attribute': 'employeeID',
                'value': 'PILOT01',
                'matched_via': 'email_cloud',
            }),
        )
        with _mock_ldap_connection() as (mock_conn, ctx_mgr):
            # Snapshot read returns an entry with old employeeID=''
            mock_conn.entries = [self._ldap_entry_with(employeeID='')]
            with patch.object(self.env['myschool.ldap.service'].__class__,
                              '_get_connection',
                              return_value=ctx_mgr):
                f.action_pilot()
        self.assertEqual(f.state, 'applied_pilot')
        self.assertTrue(f.rollback_snapshot_json)
        self.assertTrue(f.rollback_snapshot_at)
        snap = json.loads(f.rollback_snapshot_json)
        self.assertEqual(snap['attribute'], 'employeeID')
        # Both search() (for snapshot) and modify() (for apply) should
        # have run on the same connection.
        mock_conn.search.assert_called()
        mock_conn.modify.assert_called()

    def test_verify_promotes_pilot_to_done(self):
        f = self._make_finding(
            state='applied_pilot',
            proposal_kind='stamp_id',
            rollback_snapshot_json='{"source":"ad","attribute":"employeeID","old_value":""}',
        )
        f.action_verify()
        self.assertEqual(f.state, 'done')
        self.assertEqual(f.status, 'takeover_done')

    def test_verify_refuses_non_pilot_state(self):
        f = self._make_finding(state='approved',
                               proposal_kind='stamp_id')
        with self.assertRaises(UserError):
            f.action_verify()

    def test_rollback_restores_snapshot(self):
        """STAMP_ID rollback writes the old_value back via LDAP MODIFY
        and resets state to approved."""
        person = self._make_person(sap_ref='RB01')
        f = self._make_finding(
            state='applied_pilot',
            proposal_kind='stamp_id',
            matched_person_id=person.id,
            proposal_payload_json=json.dumps({
                'target_attribute': 'employeeID',
                'value': 'RB01',
            }),
            rollback_snapshot_json=json.dumps({
                'source': 'ad',
                'attribute': 'employeeID',
                'old_value': 'OLD-VALUE',
            }),
        )
        with _mock_ldap_connection() as (mock_conn, ctx_mgr):
            with patch.object(self.env['myschool.ldap.service'].__class__,
                              '_get_connection',
                              return_value=ctx_mgr):
                f.action_rollback()
        self.assertEqual(f.state, 'approved')
        self.assertFalse(f.rollback_snapshot_json)
        # MODIFY should have been called with the OLD value
        mock_conn.modify.assert_called()
        # Inspect the changes dict
        args, _kw = mock_conn.modify.call_args
        changes = args[1]
        self.assertIn('employeeID', changes)

    def test_rollback_refuses_without_snapshot(self):
        f = self._make_finding(
            state='applied_pilot',
            proposal_kind='stamp_id',
            rollback_snapshot_json=False,
        )
        with self.assertRaises(UserError):
            f.action_rollback()

    def test_pilot_failure_wipes_snapshot(self):
        """If the mutate raises, the captured snapshot is cleared so a
        retry generates a fresh one against the unchanged bron."""
        person = self._make_person(sap_ref='FAIL01')
        f = self._make_finding(
            state='approved',
            proposal_kind='stamp_id',
            matched_person_id=person.id,
            proposal_payload_json=json.dumps({
                'target_attribute': 'employeeID',
                'value': 'FAIL01',
            }),
        )
        with _mock_ldap_connection(
                modify_result={'result': 53, 'description': 'fail'}) \
                as (mock_conn, ctx_mgr):
            mock_conn.entries = [self._ldap_entry_with(employeeID='')]
            with patch.object(self.env['myschool.ldap.service'].__class__,
                              '_get_connection',
                              return_value=ctx_mgr):
                with self.assertRaises(UserError):
                    f.action_pilot()
        self.assertEqual(f.state, 'approved')
        self.assertFalse(f.rollback_snapshot_json)

    def test_rename_ad_modifies_dn(self):
        """RENAME via pilot calls modify_dn with the new RDN and
        updates self.ad_dn to the post-rename value."""
        f = self._make_finding(
            kind='group',
            ad_dn='CN=OldGroup,OU=ts,DC=test,DC=local',
            external_id='CN=OldGroup,OU=ts,DC=test,DC=local',
            state='approved',
            proposal_kind='rename',
            proposal_payload_json=json.dumps({'new_name': 'NewGroup'}),
        )
        with _mock_ldap_connection() as (mock_conn, ctx_mgr):
            with patch.object(self.env['myschool.ldap.service'].__class__,
                              '_get_connection',
                              return_value=ctx_mgr):
                f.action_pilot()
        self.assertEqual(f.state, 'applied_pilot')
        self.assertEqual(f.ad_dn, 'CN=NewGroup,OU=ts,DC=test,DC=local')
        mock_conn.modify_dn.assert_called_once_with(
            'CN=OldGroup,OU=ts,DC=test,DC=local', 'CN=NewGroup')

    def test_rename_cloud_user_rejected(self):
        """Cloud-user renaming is not supported (primaryEmail is identity)."""
        gcfg = self.env['myschool.google.workspace.config'].create({
            'name': 'Reject Google',
            'environment': 'test',
            'domain': 'test.olvp.lab',
            'subject_email': 'admin@test.olvp.lab',
            'customer_id': 'my_customer',
            'active': False,
        })
        session = self.env['myschool.ad.takeover.session'].create({
            'name': 'Reject session',
            'google_workspace_config_id': gcfg.id,
            'scope_org_id': self.school.id,
            'environment': 'test',
        })
        f = self.env['myschool.ad.takeover.finding'].create({
            'session_id': session.id,
            'kind': 'user',
            'source': 'cloud',
            'external_id': 'cloud-uid-reject',
            'ad_dn': 'reject@test.olvp.lab',
            'state': 'approved',
            'proposal_kind': 'rename',
            'proposal_payload_json': json.dumps({'new_name': 'NewMail'}),
        })
        with self.assertRaises(UserError):
            f.action_pilot()

    def test_move_ad_modifies_dn_with_new_superior(self):
        f = self._make_finding(
            kind='ou',
            ad_dn='OU=Klas-3A,OU=Klassen,DC=test,DC=local',
            external_id='OU=Klas-3A,OU=Klassen,DC=test,DC=local',
            state='approved',
            proposal_kind='move',
            proposal_payload_json=json.dumps({
                'new_parent': 'OU=Archief,DC=test,DC=local',
            }),
        )
        with _mock_ldap_connection() as (mock_conn, ctx_mgr):
            with patch.object(self.env['myschool.ldap.service'].__class__,
                              '_get_connection',
                              return_value=ctx_mgr):
                f.action_pilot()
        self.assertEqual(f.state, 'applied_pilot')
        self.assertEqual(f.ad_dn,
                         'OU=Klas-3A,OU=Archief,DC=test,DC=local')
        mock_conn.modify_dn.assert_called_once()
        args, kwargs = mock_conn.modify_dn.call_args
        # modify_dn(old_dn, new_rdn, new_superior=parent)
        self.assertEqual(args[1], 'OU=Klas-3A')
        self.assertEqual(kwargs.get('new_superior'),
                         'OU=Archief,DC=test,DC=local')

    # ------------------------------------------------------------------
    # Fase D — diff wizard
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Fase G — AD-browser tab (object_browser RPC's)
    # ------------------------------------------------------------------

    def test_ad_browser_lists_active_configs(self):
        """ad_get_ldap_configs retourneert alleen actieve configs met
        de juiste velden voor de OWL dropdown."""
        # Maak een tweede config (inactive) — moet niet in result zitten
        self.env['myschool.ldap.server.config'].create({
            'name': 'Archived Cfg',
            'environment': 'test',
            'server_url': 'ldap://archived.local',
            'port': 389,
            'base_dn': 'DC=arch,DC=local',
            'bind_dn': 'CN=admin,DC=arch,DC=local',
            'bind_password': 'dummy',
            'active': False,
        })
        configs = self.env['myschool.object.browser'].ad_get_ldap_configs()
        names = [c['name'] for c in configs]
        self.assertIn('Test LDAP', names)
        self.assertNotIn('Archived Cfg', names)
        # Verifieer velden
        for c in configs:
            self.assertIn('id', c)
            self.assertIn('environment', c)
            self.assertIn('base_dn', c)
            self.assertIn('is_active_directory', c)

    def test_ad_browser_browse_dn_missing_config(self):
        """Onbestaande config → error in result."""
        result = self.env['myschool.object.browser'].ad_browse_dn(
            999999, 'DC=anywhere')
        self.assertTrue(result.get('error'))
        self.assertIsNone(result.get('node'))

    def test_ad_browse_members_for_ou(self):
        """OU → LEVEL-search returneert group/user kinderen."""
        ou_entry = MagicMock()
        ou_entry.__contains__.side_effect = lambda k: k in (
            'distinguishedName', 'objectClass', 'member', 'memberOf')
        ou_entry.__getitem__.side_effect = lambda k: MagicMock(value={
            'distinguishedName': 'OU=foo,DC=test,DC=local',
            'objectClass': ['top', 'organizationalUnit'],
        }.get(k, None))

        group_entry = MagicMock()
        group_entry.__contains__.side_effect = lambda k: k in (
            'distinguishedName', 'objectClass', 'cn', 'mail',
            'sAMAccountName')
        group_entry.__getitem__.side_effect = lambda k: MagicMock(value={
            'distinguishedName': 'CN=teachers,OU=foo,DC=test,DC=local',
            'objectClass': ['top', 'group'],
            'cn': 'teachers', 'mail': 'teachers@x', 'sAMAccountName': 'teachers',
        }.get(k, ''))

        user_entry = MagicMock()
        user_entry.__contains__.side_effect = lambda k: k in (
            'distinguishedName', 'objectClass', 'cn', 'mail',
            'sAMAccountName')
        user_entry.__getitem__.side_effect = lambda k: MagicMock(value={
            'distinguishedName': 'CN=jan,OU=foo,DC=test,DC=local',
            'objectClass': ['top', 'person', 'organizationalPerson',
                            'user'],
            'cn': 'jan', 'mail': 'jan@x', 'sAMAccountName': 'jan',
        }.get(k, ''))

        mock_conn = MagicMock()
        def fake_search(*args, **kwargs):
            scope = kwargs.get('search_scope') or (
                args[2] if len(args) >= 3 else None)
            if scope == 'BASE':
                mock_conn.entries = [ou_entry]
            elif scope == 'LEVEL':
                mock_conn.entries = [group_entry, user_entry]
            else:
                mock_conn.entries = []
        mock_conn.search.side_effect = fake_search
        class _Ctx:
            def __enter__(self_): return mock_conn
            def __exit__(self_, *exc): return False

        ldap_cls = self.env['myschool.ldap.service'].__class__
        with patch.object(ldap_cls, '_check_ldap3_available',
                          return_value=True), \
             patch.object(ldap_cls, '_get_connection',
                          return_value=_Ctx()):
            result = self.env['myschool.object.browser'].ad_browse_members(
                self.ldap_test.id, 'OU=foo,DC=test,DC=local')
        self.assertIsNone(result.get('error'))
        members = result['members']
        self.assertEqual(len(members), 2)
        # Groups sorteren vóór users in onze ordering
        self.assertEqual(members[0]['kind'], 'group')
        self.assertEqual(members[1]['kind'], 'user')
        self.assertEqual(members[1]['mail'], 'jan@x')

    def test_ad_browse_members_for_group_resolves_member_dns(self):
        """group → member attribuut, elke DN BASE-geresolved."""
        group_entry = MagicMock()
        group_entry.__contains__.side_effect = lambda k: k in (
            'objectClass', 'member')
        group_entry.__getitem__.side_effect = lambda k: MagicMock(value={
            'objectClass': ['top', 'group'],
            'member': ['CN=jan,OU=ts,DC=test,DC=local',
                       'CN=an,OU=ts,DC=test,DC=local'],
        }.get(k, None))

        def member_entry(cn):
            e = MagicMock()
            e.__contains__.side_effect = lambda k: k in (
                'objectClass', 'cn', 'mail', 'sAMAccountName')
            e.__getitem__.side_effect = lambda k: MagicMock(value={
                'objectClass': ['top', 'person', 'organizationalPerson',
                                'user'],
                'cn': cn, 'mail': f'{cn}@x', 'sAMAccountName': cn,
            }.get(k, ''))
            return e

        mock_conn = MagicMock()
        call_n = {'n': 0}
        def fake_search(*args, **kwargs):
            call_n['n'] += 1
            scope = kwargs.get('search_scope') or (
                args[2] if len(args) >= 3 else None)
            if scope == 'BASE' and call_n['n'] == 1:
                # First BASE: the group itself
                mock_conn.entries = [group_entry]
            elif scope == 'BASE':
                # Subsequent BASEs: one member per call (alternate cn)
                cn = 'jan' if call_n['n'] == 2 else 'an'
                mock_conn.entries = [member_entry(cn)]
            else:
                mock_conn.entries = []
        mock_conn.search.side_effect = fake_search
        class _Ctx:
            def __enter__(self_): return mock_conn
            def __exit__(self_, *exc): return False

        ldap_cls = self.env['myschool.ldap.service'].__class__
        with patch.object(ldap_cls, '_check_ldap3_available',
                          return_value=True), \
             patch.object(ldap_cls, '_get_connection',
                          return_value=_Ctx()):
            result = self.env['myschool.object.browser'].ad_browse_members(
                self.ldap_test.id,
                'CN=teachers,OU=ts,DC=test,DC=local')
        self.assertIsNone(result.get('error'))
        self.assertEqual(len(result['members']), 2)
        # Alfabetisch op cn
        cns = [m['cn'] for m in result['members']]
        self.assertEqual(cns, ['an', 'jan'])

    def test_ad_browser_browse_dn_with_mocked_ldap(self):
        """Happy path met gemockte LDAP-search."""
        # Build mock entries — een OU 'foo' met één child-group.
        ou_entry = MagicMock()
        ou_entry.entry_attributes = ['distinguishedName', 'objectClass',
                                      'ou', 'description']
        ou_entry.__getitem__.side_effect = lambda k: MagicMock(value={
            'distinguishedName': 'OU=foo,DC=test,DC=local',
            'objectClass': ['top', 'organizationalUnit'],
            'ou': 'foo', 'description': 'Test OU',
        }.get(k, ''))
        ou_entry.__contains__.side_effect = lambda k: k in (
            'distinguishedName', 'objectClass', 'ou', 'description')

        child_entry = MagicMock()
        child_entry.entry_attributes = ['distinguishedName',
                                         'objectClass', 'cn']
        child_entry.__getitem__.side_effect = lambda k: MagicMock(value={
            'distinguishedName': 'CN=grp,OU=foo,DC=test,DC=local',
            'objectClass': ['top', 'group'],
            'cn': 'grp',
        }.get(k, ''))
        child_entry.__contains__.side_effect = lambda k: k in (
            'distinguishedName', 'objectClass', 'cn')

        mock_conn = MagicMock()
        # First search (BASE) returns the OU itself; second (LEVEL)
        # returns parent + child; third (size_limit child-check) returns
        # 1 result. mock_conn.entries gets set each search call.
        call_count = {'n': 0}
        def fake_search(*args, **kwargs):
            call_count['n'] += 1
            scope = kwargs.get('search_scope') or (
                args[2] if len(args) >= 3 else None)
            if scope == 'BASE':
                mock_conn.entries = [ou_entry]
            elif scope == 'LEVEL':
                # First LEVEL: children of the OU itself
                # Subsequent LEVEL with size_limit: child-existence check
                if kwargs.get('size_limit'):
                    mock_conn.entries = []  # group has no children
                else:
                    mock_conn.entries = [ou_entry, child_entry]
            else:
                mock_conn.entries = []
        mock_conn.search.side_effect = fake_search

        class _Ctx:
            def __enter__(self_):
                return mock_conn
            def __exit__(self_, *exc):
                return False

        ldap_cls = self.env['myschool.ldap.service'].__class__
        with patch.object(ldap_cls, '_check_ldap3_available',
                          return_value=True), \
             patch.object(ldap_cls, '_get_connection',
                          return_value=_Ctx()):
            result = self.env['myschool.object.browser'].ad_browse_dn(
                self.ldap_test.id, 'OU=foo,DC=test,DC=local')
        self.assertIsNone(result.get('error'))
        self.assertIsNotNone(result.get('node'))
        self.assertEqual(result['node']['kind'], 'ou')
        self.assertEqual(result['node']['cn'], 'foo')
        self.assertTrue(result['node'].get('attrs'))
        # children list should contain the group (parent gets filtered out)
        kinds = [c['kind'] for c in result['children']]
        self.assertIn('group', kinds)

    # ------------------------------------------------------------------
    # Fase F — clone prod → test
    # ------------------------------------------------------------------

    def test_clone_target_must_be_test_env(self):
        """clone_target_ldap_config_id moet environment=test hebben."""
        # Bestaande ldap_test config heeft env=test → moet OK gaan
        # via een prod-sessie. Maak eerst zo'n prod-sessie.
        prod_cfg = self.env['myschool.ldap.server.config'].create({
            'name': 'Prod for clone',
            'environment': 'prod',
            'server_url': 'ldap://prod.local',
            'port': 389,
            'base_dn': 'DC=prod,DC=local',
            'bind_dn': 'CN=admin,DC=prod,DC=local',
            'bind_password': 'dummy',
            'active': False,
        })
        # Sessie met prod-target — moet falen op env-check
        with self.assertRaises(ValidationError):
            self.env['myschool.ad.takeover.session'].create({
                'name': 'Reject target',
                'environment': 'prod',
                'ldap_config_id': prod_cfg.id,
                'clone_target_ldap_config_id': prod_cfg.id,  # prod, niet test
                'scope_org_id': self.school.id,
            })

    def test_clone_only_from_prod_session(self):
        """clone_target velden alleen toegestaan op prod-sessies."""
        with self.assertRaises(ValidationError):
            self.env['myschool.ad.takeover.session'].create({
                'name': 'Wrong env',
                'environment': 'test',
                'ldap_config_id': self.ldap_test.id,
                'clone_target_ldap_config_id': self.ldap_test.id,
                'scope_org_id': self.school.id,
            })

    def test_clone_action_refuses_test_session(self):
        """action_clone_to_test op een test-sessie raises."""
        with self.assertRaises(UserError):
            self.session.action_clone_to_test()

    def test_clone_dn_rewrite_basic(self):
        """_clone_rewrite_ad_dn vervangt prod_base door test_base."""
        cls = self.env['myschool.ad.takeover.session']
        rewritten = cls._clone_rewrite_ad_dn(
            'OU=foo,OU=bar,DC=olvp,DC=local',
            'DC=olvp,DC=local',
            'DC=lab,DC=olvp,DC=local')
        self.assertEqual(rewritten,
                         'OU=foo,OU=bar,DC=lab,DC=olvp,DC=local')

    def test_clone_dn_rewrite_outside_base_returns_none(self):
        """DN buiten prod_base wordt niet gerewriten."""
        cls = self.env['myschool.ad.takeover.session']
        result = cls._clone_rewrite_ad_dn(
            'CN=stray,DC=otherdom,DC=local',
            'DC=olvp,DC=local',
            'DC=lab,DC=olvp,DC=local')
        self.assertIsNone(result)

    def test_clone_email_rewrite(self):
        """_rewrite_email vervangt prod-domain door test-domain."""
        cls = self.env['myschool.ad.takeover.session']
        self.assertEqual(
            cls._rewrite_email('jan@olvp.be', 'olvp.be', 'test.olvp.lab'),
            'jan@test.olvp.lab')
        # Wrong domain → None
        self.assertIsNone(
            cls._rewrite_email('jan@other.com', 'olvp.be', 'test.olvp.lab'))
        # No @ → None
        self.assertIsNone(
            cls._rewrite_email('justaname', 'olvp.be', 'test.olvp.lab'))

    # ------------------------------------------------------------------
    # Fase B2 — Smartschool scanner
    # ------------------------------------------------------------------

    def _make_ss_session(self):
        """Create a session with only a SS config so the SS scanner runs
        in isolation."""
        scfg = self.env['myschool.smartschool.config'].create({
            'name': 'Test SS',
            'platform_url': 'https://test.smartschool.be',
            'api_key': 'dummy-key',
            'active': False,
        })
        session = self.env['myschool.ad.takeover.session'].create({
            'name': 'SS-only session',
            'smartschool_config_id': scfg.id,
            'scope_org_id': self.school.id,
            'environment': 'test',
        })
        return session

    @staticmethod
    def _ss_xml_users(users):
        """Build a synthetic getAllAccountsExtended XML with the given
        user-dicts. Defensive parser doesn't care about wrapper tag."""
        rows = []
        for u in users:
            fields_xml = ''.join(
                f'<{k}>{v}</{k}>' for k, v in u.items())
            rows.append(f'<row>{fields_xml}</row>')
        return f'<?xml version="1.0"?><response>{"".join(rows)}</response>'

    def _patch_ss_response(self, session, xml_text):
        """Build patches that stub the SS client + the SOAP call."""
        ss_cls = self.env['myschool.smartschool.service'].__class__
        service_obj = MagicMock()
        service_obj.getAllAccountsExtended = MagicMock(return_value=xml_text)
        client = MagicMock()
        client.service = service_obj
        return [
            patch.object(ss_cls, '_get_client', return_value=client),
        ]

    def test_ss_scan_sap_ref_match_done(self):
        """SS user with internnumber matching person.sap_ref → state=done."""
        person = self._make_person(
            sap_ref='SS01', email_cloud='ss01@test.olvp.lab')
        session = self._make_ss_session()
        xml = self._ss_xml_users([{
            'username': 'jan',
            'internnumber': 'SS01',
            'firstname': 'Jan',
            'name': 'Peeters',
            'email': 'ss01@test.olvp.lab',
        }])
        patches = self._patch_ss_response(session, xml)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            session.action_scan()
        f = session.finding_ids.filtered(lambda x: x.kind == 'user')
        self.assertEqual(len(f), 1)
        self.assertEqual(f.source, 'smartschool')
        self.assertEqual(f.state, 'done')
        self.assertEqual(f.matched_person_id, person)
        self.assertEqual(f.sap_ref, 'SS01')

    def test_ss_scan_no_internnumber_marks_orphan(self):
        """SS user without internnumber → state=proposed, link_only,
        medium-risk (cannot use STAMP_ID for SS in B2)."""
        session = self._make_ss_session()
        xml = self._ss_xml_users([{
            'username': 'noid_user',
            'internnumber': '',
            'firstname': 'No',
            'name': 'Id',
        }])
        patches = self._patch_ss_response(session, xml)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            session.action_scan()
        f = session.finding_ids.filtered(lambda x: x.kind == 'user')
        self.assertEqual(f.state, 'proposed')
        self.assertEqual(f.proposal_kind, 'link_only')
        self.assertEqual(f.risk_level, 'medium')
        self.assertIn('zonder internnumber', f.notes)

    def test_ss_scan_orphan_with_internnumber(self):
        """SS user with internnumber but no matching DB-person → orphan."""
        session = self._make_ss_session()
        xml = self._ss_xml_users([{
            'username': 'external_user',
            'internnumber': 'UNKNOWN_REF',
        }])
        patches = self._patch_ss_response(session, xml)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            session.action_scan()
        f = session.finding_ids.filtered(lambda x: x.kind == 'user')
        self.assertEqual(f.state, 'proposed')
        self.assertEqual(f.proposal_kind, 'link_only')
        self.assertIn('UNKNOWN_REF', f.notes)

    def test_ss_scan_handles_error_code(self):
        """Numeric error code from SS raises UserError with the code."""
        session = self._make_ss_session()
        patches = self._patch_ss_response(session, '1')
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with self.assertRaises(UserError):
                session.action_scan()

    def test_ss_xml_parser_defensive(self):
        """The parser must skip nodes without username/internnumber and
        still find users wrapped in arbitrary container tags."""
        session = self._make_ss_session()
        users = session._ss_parse_users(
            '<r>'
            '<row><username>a</username><internnumber>X1</internnumber></row>'
            '<other><foo>bar</foo></other>'
            '<row><username>b</username><internnumber>X2</internnumber>'
            '<email>b@x</email></row>'
            '</r>')
        self.assertEqual(len(users), 2)
        usernames = sorted(u['username'] for u in users)
        self.assertEqual(usernames, ['a', 'b'])

    # ------------------------------------------------------------------
    # Fase E — bulk-after-pilot + audit-export
    # ------------------------------------------------------------------

    def test_bulk_after_pilot_refuses_without_done_precedent(self):
        """Bulk-apply weigert als er geen state=done finding bestaat."""
        self._make_finding(state='approved', proposal_kind='link_only')
        with self.assertRaises(UserError):
            self.session.action_bulk_apply_after_pilot()

    def test_bulk_after_pilot_applies_matching_combos(self):
        """Met één done(ad,link_only) als precedent worden alle
        approved(ad,link_only) findings via action_takeover uitgevoerd."""
        # Done-precedent
        Finding = self.env['myschool.ad.takeover.finding']
        Finding.create({
            'session_id': self.session.id,
            'kind': 'ou',
            'ad_dn': 'OU=already-done,DC=test,DC=local',
            'external_id': 'OU=already-done,DC=test,DC=local',
            'source': 'ad',
            'state': 'done',
            'proposal_kind': 'link_only',
        })
        # Approved kandidaat met zelfde (source, proposal_kind)
        approved = Finding.create({
            'session_id': self.session.id,
            'kind': 'ou',
            'ad_dn': 'OU=ready,DC=test,DC=local',
            'external_id': 'OU=ready,DC=test,DC=local',
            'source': 'ad',
            'state': 'approved',
            'proposal_kind': 'link_only',
            'proposed_parent_org_id': self.school.id,
            'proposed_org_type_id': self.school.org_type_id.id,
        })
        self.session.action_bulk_apply_after_pilot()
        # action_takeover voor OU link_only roept de manual-task-service
        # aan via _takeover_ou. We verwachten state=done na succes.
        self.assertEqual(approved.state, 'done')

    def test_bulk_after_pilot_skips_unproven_combos(self):
        """Approved(ad,rename) zonder rename-precedent blijft staan."""
        Finding = self.env['myschool.ad.takeover.finding']
        Finding.create({
            'session_id': self.session.id,
            'kind': 'ou',
            'ad_dn': 'OU=lo-done,DC=test,DC=local',
            'external_id': 'OU=lo-done,DC=test,DC=local',
            'source': 'ad',
            'state': 'done',
            'proposal_kind': 'link_only',
        })
        approved_rename = Finding.create({
            'session_id': self.session.id,
            'kind': 'group',
            'ad_dn': 'CN=Rn,OU=ts,DC=test,DC=local',
            'external_id': 'CN=Rn,OU=ts,DC=test,DC=local',
            'source': 'ad',
            'state': 'approved',
            'proposal_kind': 'rename',
            'proposal_payload_json': json.dumps({'new_name': 'NewRn'}),
        })
        self.session.action_bulk_apply_after_pilot()
        self.assertEqual(approved_rename.state, 'approved',
            'rename moet ongewijzigd blijven want geen rename-precedent')

    def test_audit_export_creates_csv_attachment(self):
        """action_export_audit_report retourneert een ir.actions.act_url
        wijzend naar een ir.attachment met CSV-inhoud."""
        import base64
        self._make_finding(
            kind='user', proposal_kind='stamp_id', state='done',
            sap_ref='AUDIT01', action_message='OK',
        )
        result = self.session.action_export_audit_report()
        self.assertEqual(result.get('type'), 'ir.actions.act_url')
        # URL bevat het attachment-id
        url = result.get('url', '')
        self.assertIn('/web/content/', url)
        attachment_id = int(url.split('/web/content/')[1].split('?')[0])
        att = self.env['ir.attachment'].browse(attachment_id)
        self.assertTrue(att.exists())
        self.assertEqual(att.mimetype, 'text/csv')
        self.assertEqual(att.res_model, 'myschool.ad.takeover.session')
        self.assertEqual(att.res_id, self.session.id)
        # CSV-content moet de finding bevatten
        csv_text = base64.b64decode(att.datas).decode('utf-8')
        self.assertIn('AUDIT01', csv_text)
        self.assertIn('stamp_id', csv_text)
        self.assertIn('finding_id,source,kind', csv_text,
                      'CSV-header moet aanwezig zijn')

    def test_diff_wizard_opens_with_finding(self):
        """action_open_diff_wizard creates a wizard pointing at the
        finding and returns an act_window action."""
        f = self._make_finding(
            proposal_kind='link_only',
            state='proposed',
        )
        result = f.action_open_diff_wizard()
        self.assertEqual(result.get('type'), 'ir.actions.act_window')
        self.assertEqual(result.get('res_model'),
                         'myschool.ad.takeover.diff.wizard')
        self.assertEqual(result.get('target'), 'new')
        wiz_id = result.get('res_id')
        wiz = self.env['myschool.ad.takeover.diff.wizard'].browse(wiz_id)
        self.assertEqual(wiz.finding_id, f)

    def test_diff_wizard_actie_text_per_proposal_kind(self):
        """Each proposal_kind should produce a recognisable ACTIE
        description so the admin knows what's about to happen."""
        cases = [
            ('link_only', 'DB-record aanmaken'),
            ('stamp_id', 'STAMP_ID'),
            ('rename', 'RENAME'),
            ('move', 'MOVE'),
            ('membership_add', 'MEMBERSHIP_ADD'),
            ('delete_after', 'DELETE_AFTER'),
            ('ignore', 'IGNORE'),
        ]
        for kind, marker in cases:
            f = self._make_finding(
                ad_dn=f'CN=case-{kind},DC=test,DC=local',
                external_id=f'CN=case-{kind},DC=test,DC=local',
                proposal_kind=kind,
                proposal_payload_json=json.dumps({
                    'new_name': 'X',
                    'value': '123',
                    'new_parent': 'OU=foo',
                    'target_group_dn': 'CN=grp',
                }),
            )
            wiz = self.env['myschool.ad.takeover.diff.wizard'].create({
                'finding_id': f.id,
            })
            self.assertIn(marker, wiz.actie_text,
                f'ACTIE-text voor {kind} mist "{marker}": {wiz.actie_text}')

    def test_diff_wizard_passes_through_approve(self):
        """Wizard's action_approve must promote the underlying finding
        to state=approved."""
        f = self._make_finding(
            proposal_kind='link_only',
            state='proposed',
        )
        wiz = self.env['myschool.ad.takeover.diff.wizard'].create({
            'finding_id': f.id,
        })
        wiz.action_approve()
        self.assertEqual(f.state, 'approved')

    def test_diff_wizard_snapshot_preview_when_present(self):
        """A finding with a snapshot shows it in the wizard preview."""
        f = self._make_finding(
            proposal_kind='stamp_id',
            state='applied_pilot',
            rollback_snapshot_json=json.dumps({
                'source': 'ad',
                'attribute': 'employeeID',
                'old_value': 'OLD123',
            }),
        )
        wiz = self.env['myschool.ad.takeover.diff.wizard'].create({
            'finding_id': f.id,
        })
        self.assertIn('OLD123', wiz.snapshot_preview)
        self.assertIn('employeeID', wiz.snapshot_preview)

    def test_membership_add_ad_via_pilot(self):
        """MEMBERSHIP_ADD pilot calls ldap_service.add_group_member."""
        f = self._make_finding(
            kind='user',
            ad_dn='CN=jan,OU=ts,DC=test,DC=local',
            external_id='CN=jan,OU=ts,DC=test,DC=local',
            state='approved',
            proposal_kind='membership_add',
            proposal_payload_json=json.dumps({
                'target_group_dn': 'CN=Teachers,OU=Groups,DC=test,DC=local',
                'member_dn': 'CN=jan,OU=ts,DC=test,DC=local',
            }),
        )
        ldap_cls = self.env['myschool.ldap.service'].__class__
        with patch.object(ldap_cls, 'add_group_member',
                          return_value={'success': True, 'message': 'added'}):
            f.action_pilot()
        self.assertEqual(f.state, 'applied_pilot')
        snap = json.loads(f.rollback_snapshot_json or '{}')
        self.assertEqual(snap.get('source'), 'ad')
