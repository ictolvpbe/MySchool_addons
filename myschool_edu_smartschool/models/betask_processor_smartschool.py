# -*- coding: utf-8 -*-
import json
import logging
import secrets
import string

from odoo import api, models

_logger = logging.getLogger(__name__)


class BeTaskProcessorSmartschool(models.AbstractModel):
    """Smartschool connector-plugin op de betask-processor.

    Levert de SMARTSCHOOL/USER/* handlers + cascade-emitters die uit
    ``myschool_core`` zijn geextraheerd, en haakt ze terug aan via de
    extensiepunten. ``myschool_core`` kent Smartschool zelf niet meer
    (eenrichting: plugin -> core).
    """
    _inherit = 'myschool.betask.processor'

    @api.model
    def _get_connector_betask_handlers(self):
        handlers = super()._get_connector_betask_handlers()
        handlers.update({
            ('SMARTSCHOOL', 'USER', 'ADD'): self.process_smartschool_user_add,
            ('SMARTSCHOOL', 'USER', 'UPD'): self.process_smartschool_user_upd,
            ('SMARTSCHOOL', 'USER', 'DEACT'): self.process_smartschool_user_deact,
            ('SMARTSCHOOL', 'USER', 'PWD'): self.process_smartschool_user_pwd,
            ('SMARTSCHOOL', 'USER', 'DEL'): self.process_smartschool_user_del,
        })
        return handlers

    def _emit_connector_user_add_for_person(self, person, changes):
        super()._emit_connector_user_add_for_person(person, changes)
        self._emit_smartschool_user_add_for_person(person, changes)

    def _emit_connector_user_task(self, person, action, changes):
        super()._emit_connector_user_task(person, action, changes)
        self._emit_smartschool_user_task(person, action, changes)

    def _emit_connector_user_suspend_for_person(self, person):
        super()._emit_connector_user_suspend_for_person(person)
        if (self._is_employee_person(person)
                and person.automatic_sync
                and self._school_wants_smartschool_for_person(person)):
            try:
                self.env['myschool.betask.service'].create_task(
                    'SMARTSCHOOL', 'USER', 'DEACT', data={
                        'person_id': person.id,
                        'reason': 'Account suspend: EmployeeSuspendPeriod elapsed',
                    })
            except Exception as e:
                _logger.error(
                    '[LIFECYCLE-1] SMARTSCHOOL/USER/DEACT queue failed for %s: %s',
                    person.name, e)

    # ------------------------------------------------------------------
    # Geextraheerde Smartschool-methodes (uit myschool_core)
    # ------------------------------------------------------------------

    def _school_wants_smartschool_for_person(self, person):
        """True when there is an active ``myschool.smartschool.config`` for
        any of the orgs the person is reachable from.

        Reuses the same candidate-org set as ``_school_wants_ldap_for_person``
        (PERSON-TREE org + every PPSBR ``id_org_parent``/``id_org``) so the
        Smartschool routing matches the AD/Cloud routing. The config's own
        ``get_server_for_org`` walks ``name_tree`` upwards, so a single
        school-level config covers everything under it.
        """
        if not person:
            return False
        Config = self.env['myschool.smartschool.config']
        candidates = []
        pt_org = self._resolve_current_person_tree_org(person)
        if pt_org:
            candidates.append(pt_org)
            try:
                school = self._resolve_parent_school_from_org(pt_org)
                if school:
                    candidates.append(school)
            except Exception:
                pass
        PropRelationType = self.env['myschool.proprelation.type']
        PropRelation = self.env['myschool.proprelation']
        ppsbr_type = PropRelationType.search(
            [('name', '=', self.PROPRELATION_TYPE_PPSBR)], limit=1)
        if ppsbr_type:
            ppsbrs = PropRelation.search([
                ('id_person', '=', person.id),
                ('proprelation_type_id', '=', ppsbr_type.id),
                ('is_active', '=', True),
            ])
            for rel in ppsbrs:
                if rel.id_org_parent:
                    candidates.append(rel.id_org_parent)
                if rel.id_org:
                    candidates.append(rel.id_org)
        for org in candidates:
            if Config.get_server_for_org(org):
                return True
        return False

    def _emit_smartschool_user_add_for_person(self, person, changes):
        """Queue a SMARTSCHOOL/USER/ADD task for a person if their school has
        a Smartschool platform configured.

        Same queue-only philosophy as ``_emit_cloud_user_add_for_person``:
        the actual provisioning happens later in
        ``process_smartschool_user_add`` (Fase 3) which re-resolves the
        person's school + platform at execution time, so the most up-to-date
        role/tree position wins. Dedupes against pending tasks for the same
        person.

        Honours ``person.automatic_sync=False`` as a veto so admins can
        opt-out specific persons from Smartschool provisioning.
        """
        if not person:
            return
        if not self._is_employee_person(person):
            return
        if not person.automatic_sync:
            return
        if not self._school_wants_smartschool_for_person(person):
            return
        BeTask = self.env['myschool.betask']
        BeTaskType = self.env['myschool.betask.type']
        task_type = BeTaskType.search([
            ('target', '=', 'SMARTSCHOOL'),
            ('object', '=', 'USER'),
            ('action', '=', 'ADD'),
        ], limit=1)
        if not task_type:
            _logger.warning('[SMARTSCHOOL-CASCADE] SMARTSCHOOL/USER/ADD task type missing')
            return
        existing = BeTask.search([
            ('betasktype_id', '=', task_type.id),
            ('status', '=', 'new'),
            ('data', 'ilike', f'"person_id": {person.id}'),
        ], limit=1)
        if existing:
            return
        BeTask.create({
            'name': f'SMARTSCHOOL/USER/ADD for {person.name}',
            'betasktype_id': task_type.id,
            'status': 'new',
            'data': json.dumps({'person_id': person.id}),
        })
        changes.append(f'Queued SMARTSCHOOL/USER/ADD for {person.name}')

    def _resolve_smartschool_config_for_person(self, person):
        """Return the Smartschool config that serves ``person``'s school.

        Reuses the same candidate-org walk as ``_school_wants_smartschool_for_person``
        (PERSON-TREE org + every PPSBR ``id_org_parent``/``id_org``).
        Returns an empty recordset when no platform is configured.
        """
        Config = self.env['myschool.smartschool.config']
        if not person:
            return Config.browse()
        candidates = []
        pt_org = self._resolve_current_person_tree_org(person)
        if pt_org:
            candidates.append(pt_org)
            try:
                school = self._resolve_parent_school_from_org(pt_org)
                if school:
                    candidates.append(school)
            except Exception:
                pass
        PropRelationType = self.env['myschool.proprelation.type']
        PropRelation = self.env['myschool.proprelation']
        ppsbr_type = PropRelationType.search(
            [('name', '=', self.PROPRELATION_TYPE_PPSBR)], limit=1)
        if ppsbr_type:
            ppsbrs = PropRelation.search([
                ('id_person', '=', person.id),
                ('proprelation_type_id', '=', ppsbr_type.id),
                ('is_active', '=', True),
            ])
            for rel in ppsbrs:
                if rel.id_org_parent:
                    candidates.append(rel.id_org_parent)
                if rel.id_org:
                    candidates.append(rel.id_org)
        for org in candidates:
            cfg = Config.get_server_for_org(org)
            if cfg:
                return cfg
        return Config.browse()

    def _smartschool_username_for_person(self, person):
        """Smartschool ``userIdentifier`` = local-part of email_cloud.

        Returns None when no email_cloud is set — caller must handle that
        as a hard failure (we can't create an account without a username).
        """
        if not person or not person.email_cloud:
            return None
        local = person.email_cloud.split('@', 1)[0].strip()
        return local or None

    def _smartschool_generate_password(self):
        """Random 12-char password meeting Smartschool complexity rules.

        Forces at least one upper / lower / digit / punctuation, then
        randomises the remaining 8 chars. ``secrets`` over ``random`` for
        crypto-grade entropy (random module is already imported but is
        not safe for passwords).
        """
        import secrets
        alphabet = string.ascii_letters + string.digits + '!@#$%'
        chars = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice('!@#$%'),
        ]
        chars += [secrets.choice(alphabet) for _ in range(8)]
        # Shuffle with secrets-grade RNG too.
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        return ''.join(chars)

    def _smartschool_build_save_user_payload(self, person, config, password=None):
        """Map a ``myschool.person`` + config to ``saveUser`` kwargs.

        Field names follow the WSDL the OLVP Smartschool platforms expose
        (Vlaams-NL variant):
          username, internnumber, stamboeknummer, name, surname, extranames,
          initials, sex, birthday, birthplace, birthcountry, address,
          postalcode, location, country, email, mobilephone, homephone, fax,
          prn, untis, basisrol, passwd1/2/3

        MVP scope: only the fields needed for leerkrachten. Optional fields
        (sex, address, birthday, ...) are sent empty — Smartschool keeps the
        existing remote value when a field is empty on update, so we don't
        accidentally erase data the school admin maintains by hand.
        """
        sap_ref = person.sap_ref or ''
        # ``internnumber`` is our idempotency key on Smartschool.
        # ``stamboeknummer`` (rijksregister) and ``prn`` (persoonlijk
        # referentienummer) are kept empty for MVP: they have specific
        # legal formats in Vlaams onderwijs and putting the internal SAP
        # ref in there triggered error 23 ("onbekende fout") server-side.
        payload = {
            'username': self._smartschool_username_for_person(person),
            'internnumber': sap_ref,
            'stamboeknummer': '',
            'name': person.first_name or '',
            'surname': person.last_name or '',
            'extranames': '',
            'initials': person.abbreviation or '',
            'sex': '',
            'birthday': '',
            'birthplace': '',
            'birthcountry': '',
            'address': '',
            'postalcode': '',
            'location': '',
            'country': '',
            'email': person.email_cloud or '',
            'mobilephone': '',
            'homephone': '',
            'fax': '',
            'prn': '',
            'untis': '',
            'basisrol': config.default_role_teacher or 'Leerkracht',
        }
        if password is not None:
            payload['passwd1'] = password
            payload['passwd2'] = ''
            payload['passwd3'] = ''
        return payload

    @api.model
    def process_smartschool_user_add(self, task):
        """SMARTSCHOOL/USER/ADD — upsert a teacher account via saveUser.

        Steps:
          1. Resolve person + config (skip if either missing).
          2. EMPLOYEE-only guard (defense-in-depth — emitter already filters).
          3. Ownership-check: pre-existing account with mismatched
             internnumber → skip + audit, never overwrite.
          4. saveUser with full payload (random password only for new
             users; updates omit ``passwd1`` so we don't reset existing
             passwords on routine syncs).
          5. Optional forcePasswordReset when config.force_password_reset
             AND we just created the account.
        """
        _logger.info(f'Processing SMARTSCHOOL_USER_ADD: {task.name}')
        data = self._parse_task_data(task.data) or {}
        person_id = data.get('person_id') if isinstance(data, dict) else None
        if not person_id:
            return {'success': False, 'error': 'Missing person_id in task data'}

        person = self.env['myschool.person'].browse(person_id).exists()
        if not person:
            return {'success': False,
                    'error': f'Person {person_id} not found'}

        if not self._is_employee_person(person):
            return {'success': True,
                    'changes': f'Skipped: {person.name} is not EMPLOYEE (MVP scope)'}

        config = self._resolve_smartschool_config_for_person(person)
        if not config:
            return {'success': True,
                    'changes': f'Skipped: no Smartschool config for {person.name}'}

        username = self._smartschool_username_for_person(person)
        if not username:
            return {'success': False,
                    'error': f'Cannot derive Smartschool username — '
                             f'{person.name} has no email_cloud'}

        svc = self.env['myschool.smartschool.service']
        ownership = svc.check_ownership(
            config, username, person.sap_ref or '', person=person)
        if not ownership['owned']:
            return {
                'success': True,
                'changes': (f'Skipped: pre-existing Smartschool user {username!r} '
                            f'has internnumber {ownership["existing_internnumber"]!r}, '
                            f'expected {person.sap_ref!r}'),
            }

        is_new_user = ownership['existing_internnumber'] is None
        password = self._smartschool_generate_password() if is_new_user else None

        payload = self._smartschool_build_save_user_payload(
            person, config, password=password)
        result = svc._call(config, 'saveUser',
                           mutating=True, person=person, **payload)

        if not result.get('success'):
            return {'success': False,
                    'error': f'saveUser failed: {result.get("message")}'}

        changes = []
        if result.get('dry_run'):
            changes.append(f'[DRY RUN] saveUser would {"create" if is_new_user else "update"} {username}')
        elif is_new_user:
            changes.append(f'Created Smartschool user {username} for {person.name}')
            # Het initiële wachtwoord wordt NIET gelogd (lekt naar log +
            # eventueel sys.event). Het wordt hieronder op person.password
            # bewaard zodat een LETTER/USER/GENERATE-cascade het later naar
            # de gebruiker kan mailen — TODO Fase 4.
            _logger.info('[SMARTSCHOOL] Created %s (initieel wachtwoord gezet)',
                         username)
            # Persist on person.password so a LETTER template can pick
            # it up via ``{{ object.password }}`` later.
            try:
                person.sudo().write({'password': password})
            except Exception as e:
                _logger.warning(
                    '[SMARTSCHOOL] could not store password on person.%s: %s',
                    person.id, e)
        else:
            changes.append(f'Updated Smartschool user {username} for {person.name}')

        if is_new_user and config.force_password_reset and not result.get('dry_run'):
            try:
                reset_result = svc._call(
                    config, 'forcePasswordReset',
                    mutating=True, person=person,
                    userIdentifier=username,
                    accountType='1')
                if reset_result.get('success'):
                    changes.append('forcePasswordReset OK')
                else:
                    changes.append(
                        f'WARN: forcePasswordReset failed: {reset_result.get("message")}')
            except Exception as e:
                _logger.warning(
                    '[SMARTSCHOOL] forcePasswordReset raised for %s: %s', username, e)
                changes.append(f'WARN: forcePasswordReset exception: {e}')

        return {'success': True, 'changes': '\n'.join(changes)}

    @api.model
    def process_smartschool_user_upd(self, task):
        """SMARTSCHOOL/USER/UPD — saveUser is upsert, so delegate to ADD.

        The ADD path already handles the existing-user case (skips the
        password, runs the ownership-check). Duplicating logic here would
        only mean two paths to keep in sync.
        """
        return self.process_smartschool_user_add(task)

    @api.model
    def process_smartschool_user_deact(self, task):
        """SMARTSCHOOL/USER/DEACT — set account status to inactive.

        Called from ``cron_employee_account_lifecycle`` phase 1. The
        person record may already be ``is_active=False`` at this point,
        so we browse with ``active_test=False``.
        """
        _logger.info(f'Processing SMARTSCHOOL_USER_DEACT: {task.name}')
        data = self._parse_task_data(task.data) or {}
        person_id = data.get('person_id') if isinstance(data, dict) else None
        if not person_id:
            return {'success': False, 'error': 'Missing person_id'}

        person = self.env['myschool.person'].with_context(
            active_test=False).browse(person_id).exists()
        if not person:
            return {'success': False, 'error': f'Person {person_id} not found'}

        config = self._resolve_smartschool_config_for_person(person)
        if not config:
            return {'success': True,
                    'changes': f'Skipped: no Smartschool config for {person.name}'}

        username = self._smartschool_username_for_person(person)
        if not username:
            return {'success': True,
                    'changes': f'Skipped: no Smartschool username for {person.name}'}

        svc = self.env['myschool.smartschool.service']
        ownership = svc.check_ownership(
            config, username, person.sap_ref or '', person=person)
        if ownership['existing_internnumber'] is None:
            return {'success': True,
                    'changes': f'Skipped: {username!r} does not exist on Smartschool'}
        if not ownership['owned']:
            return {'success': True,
                    'changes': f'Skipped: {username!r} not MySchool-managed'}

        result = svc._call(
            config, 'setAccountStatus',
            mutating=True, person=person,
            userIdentifier=username,
            accountStatus='inactive')
        if not result.get('success'):
            return {'success': False,
                    'error': f'setAccountStatus failed: {result.get("message")}'}
        msg = (f'[DRY RUN] would deactivate {username}'
               if result.get('dry_run')
               else f'Deactivated Smartschool user {username}')
        return {'success': True, 'changes': msg}

    @api.model
    def process_smartschool_user_pwd(self, task):
        """SMARTSCHOOL/USER/PWD — set / rotate the user's password.

        Data: ``{'person_id': N, 'password': '<optional>',
                 'change_at_next_login': True/False (optional)}``.
        When ``password`` is omitted, a fresh random one is generated
        and persisted on ``person.password`` so a follow-up letter
        template can pick it up.
        """
        _logger.info(f'Processing SMARTSCHOOL_USER_PWD: {task.name}')
        data = self._parse_task_data(task.data) or {}
        person_id = data.get('person_id') if isinstance(data, dict) else None
        if not person_id:
            return {'success': False, 'error': 'Missing person_id'}
        person = self.env['myschool.person'].browse(person_id).exists()
        if not person:
            return {'success': False, 'error': f'Person {person_id} not found'}

        config = self._resolve_smartschool_config_for_person(person)
        if not config:
            return {'success': True,
                    'changes': f'Skipped: no Smartschool config for {person.name}'}

        username = self._smartschool_username_for_person(person)
        if not username:
            return {'success': False,
                    'error': f'No Smartschool username for {person.name}'}

        svc = self.env['myschool.smartschool.service']
        ownership = svc.check_ownership(
            config, username, person.sap_ref or '', person=person)
        if not ownership['owned']:
            return {'success': True,
                    'changes': f'Skipped: {username!r} not MySchool-managed'}

        password = data.get('password') or self._smartschool_generate_password()
        change_at_next = data.get('change_at_next_login',
                                  config.force_password_reset)

        result = svc._call(
            config, 'savePassword',
            mutating=True, person=person,
            userIdentifier=username,
            password=password,
            accountType='1',
            changePasswordAtNextLogin='1' if change_at_next else '0')
        if not result.get('success'):
            return {'success': False,
                    'error': f'savePassword failed: {result.get("message")}'}

        if not result.get('dry_run'):
            try:
                person.sudo().write({'password': password})
            except Exception as e:
                _logger.warning(
                    '[SMARTSCHOOL] could not store rotated password on person.%s: %s',
                    person.id, e)

        msg = (f'[DRY RUN] would rotate password for {username}'
               if result.get('dry_run')
               else f'Rotated Smartschool password for {username}')
        return {'success': True, 'changes': msg}

    @api.model
    def process_smartschool_user_del(self, task):
        """SMARTSCHOOL/USER/DEL — permanent delete via delUser.

        Used by Phase 2 of the account lifecycle. Requires
        ``requires_confirmation=True`` on the task type (registered in
        smartschool_task_types.xml) so it never auto-runs without
        explicit admin approval.
        """
        _logger.info(f'Processing SMARTSCHOOL_USER_DEL: {task.name}')
        data = self._parse_task_data(task.data) or {}
        person_id = data.get('person_id') if isinstance(data, dict) else None
        if not person_id:
            return {'success': False, 'error': 'Missing person_id'}

        person = self.env['myschool.person'].with_context(
            active_test=False).browse(person_id).exists()
        if not person:
            return {'success': False, 'error': f'Person {person_id} not found'}

        config = self._resolve_smartschool_config_for_person(person)
        if not config:
            return {'success': True,
                    'changes': f'Skipped: no Smartschool config for {person.name}'}

        username = self._smartschool_username_for_person(person)
        if not username:
            return {'success': True,
                    'changes': f'Skipped: no Smartschool username for {person.name}'}

        svc = self.env['myschool.smartschool.service']
        ownership = svc.check_ownership(
            config, username, person.sap_ref or '', person=person)
        if ownership['existing_internnumber'] is None:
            return {'success': True,
                    'changes': f'Skipped: {username!r} already absent on Smartschool'}
        if not ownership['owned']:
            return {'success': True,
                    'changes': f'Skipped: {username!r} not MySchool-managed'}

        result = svc._call(
            config, 'delUser',
            mutating=True, person=person,
            userIdentifier=username,
            officialDate='')
        if not result.get('success'):
            return {'success': False,
                    'error': f'delUser failed: {result.get("message")}'}
        msg = (f'[DRY RUN] would delete {username}'
               if result.get('dry_run')
               else f'Deleted Smartschool user {username}')
        return {'success': True, 'changes': msg}

    @api.model
    def _emit_smartschool_user_task(self, person, action, changes):
        """Queue *and run* a SMARTSCHOOL/USER/<action> betask for ``person``.

        Same MVP gates as the betask_processor emitter:
          * ``_is_employee_person`` — leerkrachten only
          * ``_school_wants_smartschool_for_person`` — school must have an
            active ``myschool.smartschool.config``

        ``action`` is one of ADD / UPD / DEACT / PWD. DEL is intentionally
        NOT supported here — that path requires admin confirmation via the
        lifecycle cron, not from the manual processor.

        Skips silently when the gates reject so manual flows for non-EMPLOYEE
        persons or non-Smartschool schools are unaffected.
        """
        if not person:
            return
        processor = self.env['myschool.betask.processor']
        if not processor._is_employee_person(person):
            return
        if not person.automatic_sync:
            return
        if not processor._school_wants_smartschool_for_person(person):
            return
        label = (f"SMARTSCHOOL/USER/{action} for "
                 f"{person.first_name} {person.name}")
        changes.append(f"Queued {label}")
        self._create_and_run_task('SMARTSCHOOL', 'USER', action, {
            'person_id': person.id,
        }, changes, label=label)
