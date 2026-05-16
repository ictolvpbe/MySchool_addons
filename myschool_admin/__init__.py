from . import models
from . import controllers


def _migrate_ad_takeover_phase_a_post_init(env):
    """Phase-A migration for myschool.ad.takeover.{session,finding}.

    Backfills the new source/external_id/state/proposal_kind/matched_*
    columns on existing finding rows from the legacy status/match_kind
    columns, and tags pre-existing LDAP/Google configs as ``prod``.

    Idempotent: re-running on already-migrated rows is a no-op because
    the WHERE clauses skip rows that already have the new fields filled.
    """
    # ----- ldap/google configs: default to 'prod' for any row that
    # somehow ended up without an environment value. Default in the
    # field declaration already handles fresh inserts; this catches
    # pre-existing rows where the column gets added without a default.
    cr = env.cr
    for table in ('myschool_ldap_server_config',
                  'myschool_google_workspace_config'):
        cr.execute(f"""
            UPDATE {table}
               SET environment = 'prod'
             WHERE environment IS NULL
        """)
        if cr.rowcount:
            _log(env, 'INFO',
                 f'Tagged {cr.rowcount} {table} row(s) as environment=prod.')

    # ----- ad-takeover sessions: default environment + current_phase
    # for legacy sessions. Existing sessions were against prod LDAP
    # configs (no test concept existed yet).
    cr.execute("""
        UPDATE myschool_ad_takeover_session
           SET environment = 'prod'
         WHERE environment IS NULL
    """)
    if cr.rowcount:
        _log(env, 'INFO',
             f'Tagged {cr.rowcount} ad-takeover session(s) as prod.')

    # Phase: existing sessions skip pre-flight entirely (the concept
    # didn't exist). If all their findings were resolved → 'done',
    # otherwise → 'link' (they were already past pre-flight by design).
    cr.execute("""
        UPDATE myschool_ad_takeover_session s
           SET current_phase = CASE
               WHEN NOT EXISTS (
                   SELECT 1 FROM myschool_ad_takeover_finding f
                    WHERE f.session_id = s.id
                      AND f.status NOT IN ('takeover_done', 'delete_done',
                                           'matched', 'ignored')
               ) THEN 'done'
               ELSE 'link'
           END
         WHERE current_phase IS NULL
    """)
    if cr.rowcount:
        _log(env, 'INFO',
             f'Set current_phase on {cr.rowcount} legacy session(s).')

    # ----- findings: backfill source/external_id/state/proposal_kind.
    # Existing rows are all AD (the only scanner that existed).
    cr.execute("""
        UPDATE myschool_ad_takeover_finding
           SET source = 'ad'
         WHERE source IS NULL
    """)

    cr.execute("""
        UPDATE myschool_ad_takeover_finding
           SET external_id = ad_dn
         WHERE external_id IS NULL
           AND ad_dn IS NOT NULL
    """)

    cr.execute("""
        UPDATE myschool_ad_takeover_finding
           SET risk_level = 'low'
         WHERE risk_level IS NULL
    """)

    # state + proposal_kind from legacy status. Pairs mirror
    # LEGACY_STATUS_MIGRATION in ad_takeover.py.
    status_map = {
        'investigate':            ('discovered', None),
        'takeover_pending':       ('proposed',   'link_only'),
        'takeover_done':          ('done',       'link_only'),
        'delete_after_migration': ('proposed',   'delete_after'),
        'delete_done':            ('done',       'delete_after'),
        'matched':                ('done',       None),
        'ignored':                ('ignored',    'ignore'),
    }
    migrated = 0
    for legacy_status, (new_state, new_proposal) in status_map.items():
        cr.execute("""
            UPDATE myschool_ad_takeover_finding
               SET state = %s,
                   proposal_kind = %s
             WHERE status = %s
               AND state IS NULL
        """, (new_state, new_proposal, legacy_status))
        migrated += cr.rowcount

    if migrated:
        _log(env, 'INFO',
             f'Migrated {migrated} ad-takeover finding(s) to new state.')

    # matched_*: best-effort recompute via the FQDN-fields. We only
    # populate when both the finding's ad_dn and the DB record match
    # exactly — fuzzy/email matches stay for the Fase B linker so we
    # don't overwrite cleaner data later.
    cr.execute("""
        UPDATE myschool_ad_takeover_finding f
           SET matched_org_id = o.id
          FROM myschool_org o
         WHERE f.matched_org_id IS NULL
           AND f.kind = 'ou'
           AND f.ad_dn IS NOT NULL
           AND LOWER(o.ou_fqdn_internal) = LOWER(f.ad_dn)
    """)
    cr.execute("""
        UPDATE myschool_ad_takeover_finding f
           SET matched_org_id = o.id
          FROM myschool_org o
         WHERE f.matched_org_id IS NULL
           AND f.kind = 'group'
           AND f.ad_dn IS NOT NULL
           AND (LOWER(o.com_group_fqdn_internal) = LOWER(f.ad_dn)
                OR LOWER(o.sec_group_fqdn_internal) = LOWER(f.ad_dn))
    """)
    cr.execute("""
        UPDATE myschool_ad_takeover_finding f
           SET matched_person_id = p.id
          FROM myschool_person p
         WHERE f.matched_person_id IS NULL
           AND f.kind = 'user'
           AND f.ad_dn IS NOT NULL
           AND LOWER(p.person_fqdn_internal) = LOWER(f.ad_dn)
    """)


def _log(env, level, message):
    env['ir.logging'].sudo().create({
        'name': 'myschool_admin.migrate',
        'type': 'server',
        'level': level,
        'message': message,
        'path': '__init__',
        'func': '_migrate_ad_takeover_phase_a_post_init',
        'line': '0',
    })
