from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError, AccessError
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'myschool_projects')
class TestProjectModel(TransactionCase):
    """Unit tests voor het myschool.project(.task) datamodel:
    voortgang-rollup, hiërarchie, milestone-anker, constraints en tags.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.P = cls.env['myschool.project']
        cls.T = cls.env['myschool.project.task']
        cls.Tag = cls.env['myschool.project.tag']
        cls.Cat = cls.env['myschool.project.category']

    # ---------------- voortgang / rollup ----------------

    def test_rollup_over_subprojects(self):
        parent = self.P.create({'name': 'P'})
        self.P.create({'name': 'A', 'parent_id': parent.id, 'progress_own': 80})
        self.P.create({'name': 'B', 'parent_id': parent.id, 'progress_own': 40})
        parent.invalidate_recordset()
        self.assertEqual(parent.progress, 60.0)

    def test_progress_from_leaf_tasks(self):
        proj = self.P.create({'name': 'P'})
        self.T.create({'name': 't1', 'project_id': proj.id, 'state': 'done'})
        self.T.create({'name': 't2', 'project_id': proj.id, 'state': 'todo'})
        proj.invalidate_recordset()
        self.assertEqual(proj.progress, 50.0)

    def test_milestone_excluded_from_progress(self):
        proj = self.P.create({'name': 'P'})
        self.T.create({'name': 't1', 'project_id': proj.id, 'state': 'done'})
        self.T.create({'name': 'm', 'project_id': proj.id,
                       'item_type': 'milestone', 'state': 'todo'})
        proj.invalidate_recordset()
        # alleen de echte taak telt → 1/1 = 100%
        self.assertEqual(proj.progress, 100.0)

    def test_summary_parent_not_double_counted(self):
        proj = self.P.create({'name': 'P'})
        phase = self.T.create({'name': 'phase', 'project_id': proj.id, 'item_type': 'phase'})
        self.T.create({'name': 't1', 'project_id': proj.id, 'parent_id': phase.id, 'state': 'done'})
        self.T.create({'name': 't2', 'project_id': proj.id, 'parent_id': phase.id, 'state': 'todo'})
        proj.invalidate_recordset()
        # phase (heeft kinderen) telt niet mee → 1/2 leaf-taken done
        self.assertEqual(proj.progress, 50.0)

    def test_cancelled_excluded(self):
        proj = self.P.create({'name': 'P'})
        self.T.create({'name': 't1', 'project_id': proj.id, 'state': 'done'})
        self.T.create({'name': 't2', 'project_id': proj.id, 'state': 'cancelled'})
        proj.invalidate_recordset()
        self.assertEqual(proj.progress, 100.0)

    def test_task_counts(self):
        proj = self.P.create({'name': 'P'})
        self.T.create({'name': 't1', 'project_id': proj.id, 'state': 'done'})
        self.T.create({'name': 't2', 'project_id': proj.id, 'state': 'todo'})
        self.T.create({'name': 'm', 'project_id': proj.id, 'item_type': 'milestone'})
        proj.invalidate_recordset()
        self.assertEqual(proj.task_count, 2)
        self.assertEqual(proj.done_task_count, 1)
        self.assertEqual(proj.open_task_count, 1)
        self.assertEqual(proj.milestone_count, 1)

    # ---------------- milestone-anker ----------------

    def test_milestone_progress(self):
        proj = self.P.create({'name': 'P'})
        ms = self.T.create({'name': 'ms', 'project_id': proj.id, 'item_type': 'milestone'})
        self.T.create({'name': 't1', 'project_id': proj.id, 'milestone_id': ms.id, 'state': 'done'})
        self.T.create({'name': 't2', 'project_id': proj.id, 'milestone_id': ms.id, 'state': 'todo'})
        self.T.create({'name': 't3', 'project_id': proj.id, 'milestone_id': ms.id, 'state': 'done'})
        ms.invalidate_recordset()
        self.assertEqual(round(ms.milestone_progress), 67)

    def test_milestone_id_must_be_milestone(self):
        proj = self.P.create({'name': 'P'})
        t1 = self.T.create({'name': 't1', 'project_id': proj.id})  # gewone taak
        t2 = self.T.create({'name': 't2', 'project_id': proj.id})
        with self.assertRaises(ValidationError):
            t2.milestone_id = t1.id
            t2.flush_recordset()

    def test_milestone_id_same_project(self):
        p1 = self.P.create({'name': 'P1'})
        p2 = self.P.create({'name': 'P2'})
        ms = self.T.create({'name': 'm', 'project_id': p2.id, 'item_type': 'milestone'})
        t = self.T.create({'name': 't', 'project_id': p1.id})
        with self.assertRaises(ValidationError):
            t.milestone_id = ms.id
            t.flush_recordset()

    # ---------------- hiërarchie & constraints ----------------

    def test_task_child_count(self):
        proj = self.P.create({'name': 'P'})
        phase = self.T.create({'name': 'phase', 'project_id': proj.id, 'item_type': 'phase'})
        self.T.create({'name': 'a', 'project_id': proj.id, 'parent_id': phase.id})
        self.T.create({'name': 'b', 'project_id': proj.id, 'parent_id': phase.id})
        phase.invalidate_recordset()
        self.assertEqual(phase.child_count, 2)

    def test_project_no_cycle(self):
        a = self.P.create({'name': 'A'})
        b = self.P.create({'name': 'B', 'parent_id': a.id})
        with self.assertRaises(UserError):
            a.parent_id = b.id
            a.flush_recordset()

    def test_task_no_cycle(self):
        proj = self.P.create({'name': 'P'})
        a = self.T.create({'name': 'a', 'project_id': proj.id})
        b = self.T.create({'name': 'b', 'project_id': proj.id, 'parent_id': a.id})
        with self.assertRaises(UserError):
            a.parent_id = b.id
            a.flush_recordset()

    def test_task_cross_project_parent(self):
        p1 = self.P.create({'name': 'P1'})
        p2 = self.P.create({'name': 'P2'})
        t1 = self.T.create({'name': 't1', 'project_id': p1.id})
        t2 = self.T.create({'name': 't2', 'project_id': p2.id})
        with self.assertRaises(ValidationError):
            t1.parent_id = t2.id
            t1.flush_recordset()

    def test_self_dependency(self):
        proj = self.P.create({'name': 'P'})
        t = self.T.create({'name': 't', 'project_id': proj.id})
        with self.assertRaises(ValidationError):
            t.depends_on_ids = [(4, t.id)]
            t.flush_recordset()

    @mute_logger('odoo.sql_db')
    def test_project_code_unique(self):
        self.P.create({'name': 'P1', 'code': 'X'})
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.P.create({'name': 'P2', 'code': 'X'})
                self.env.flush_all()

    # ---------------- tags ----------------

    def test_tag_assignment(self):
        proj = self.P.create({'name': 'P'})
        tg = self.Tag.create({'name': 'urgent'})
        t = self.T.create({'name': 't', 'project_id': proj.id, 'tag_ids': [(6, 0, [tg.id])]})
        self.assertEqual(t.tag_ids.mapped('name'), ['urgent'])

    @mute_logger('odoo.sql_db')
    def test_tag_name_unique(self):
        self.Tag.create({'name': 'urgent'})
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Tag.create({'name': 'urgent'})
                self.env.flush_all()

    # ---------------- category ----------------

    def test_category_assignment_and_count(self):
        cat = self.Cat.create({'name': 'ICT'})
        self.P.create({'name': 'P1', 'category_id': cat.id})
        self.P.create({'name': 'P2', 'category_id': cat.id})
        cat.invalidate_recordset()
        self.assertEqual(cat.project_count, 2)

    @mute_logger('odoo.sql_db')
    def test_category_name_unique(self):
        self.Cat.create({'name': 'ICT'})
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Cat.create({'name': 'ICT'})
                self.env.flush_all()

    # ---------------- templates ----------------

    def test_template_instantiation(self):
        tmpl = self.P.create({'name': 'Blueprint', 'code': 'BP', 'is_template': True})
        phase = self.T.create({'name': 'Phase 1', 'project_id': tmpl.id, 'item_type': 'phase'})
        ms = self.T.create({'name': 'MS', 'project_id': tmpl.id, 'item_type': 'milestone'})
        a = self.T.create({'name': 'A', 'project_id': tmpl.id,
                           'parent_id': phase.id, 'milestone_id': ms.id})
        self.T.create({'name': 'B', 'project_id': tmpl.id,
                       'parent_id': phase.id, 'depends_on_ids': [(4, a.id)]})
        sub = self.P.create({'name': 'Sub', 'parent_id': tmpl.id, 'is_template': True})
        self.T.create({'name': 'S1', 'project_id': sub.id})

        action = tmpl.action_create_from_template()
        new = self.P.browse(action['res_id'])
        self.assertFalse(new.is_template)
        self.assertFalse(new.code)                       # code niet gekopieerd (uniek)
        self.assertEqual(new.state, 'new')
        self.assertEqual(len(new.task_ids), 4)
        new_a = new.task_ids.filtered(lambda t: t.name == 'A')
        new_b = new.task_ids.filtered(lambda t: t.name == 'B')
        new_phase = new.task_ids.filtered(lambda t: t.name == 'Phase 1')
        new_ms = new.task_ids.filtered(lambda t: t.name == 'MS')
        # hiërarchie + milestone + dependency geremapt binnen de kopie
        self.assertEqual(new_a.parent_id, new_phase)
        self.assertEqual(new_a.milestone_id, new_ms)
        self.assertEqual(new_b.depends_on_ids, new_a)
        # verwijst NIET naar de originele template-taken
        self.assertNotIn(a.id, new.task_ids.ids)
        # sub-project mee gekopieerd, niet langer een template
        self.assertEqual(len(new.child_ids), 1)
        self.assertFalse(new.child_ids.is_template)
        self.assertEqual(len(new.child_ids.task_ids), 1)

    def test_create_from_template_requires_template(self):
        proj = self.P.create({'name': 'Normaal'})
        with self.assertRaises(UserError):
            proj.action_create_from_template()

    # ---------------- access / rollen (record rules) ----------------

    @classmethod
    def _mk_user(cls, login, group_xmlid):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'group_ids': [(6, 0, [cls.env.ref(group_xmlid).id])],
        })

    def test_access_member_roles(self):
        owner = self._mk_user('p_owner', 'myschool_projects.group_projects_user')
        reader = self._mk_user('p_reader', 'myschool_projects.group_projects_user')
        outsider = self._mk_user('p_out', 'myschool_projects.group_projects_user')
        proj = self.P.create({'name': 'Secret', 'responsible_id': owner.id})
        self.env['myschool.project.membership'].create({
            'project_id': proj.id, 'user_id': reader.id, 'role': 'reader'})

        # responsible (owner) ziet + mag bewerken
        self.assertEqual(proj.with_user(owner).name, 'Secret')
        proj.with_user(owner).write({'name': 'Renamed'})
        # reader ziet maar mag NIET bewerken
        self.assertTrue(proj.with_user(reader).read(['name']))
        with self.assertRaises(AccessError):
            proj.with_user(reader).write({'name': 'Nope'})
        # outsider ziet het project niet
        self.assertFalse(self.P.with_user(outsider).search([('id', '=', proj.id)]))

    def test_access_editor_can_write(self):
        owner = self._mk_user('p_o2', 'myschool_projects.group_projects_user')
        editor = self._mk_user('p_ed', 'myschool_projects.group_projects_user')
        proj = self.P.create({'name': 'P', 'responsible_id': owner.id})
        self.env['myschool.project.membership'].create({
            'project_id': proj.id, 'user_id': editor.id, 'role': 'editor'})
        proj.with_user(editor).write({'name': 'edited-by-editor'})
        self.assertEqual(proj.name, 'edited-by-editor')

    def test_access_see_all_overrides(self):
        seer = self._mk_user('p_seeall', 'myschool_projects.group_projects_see_all')
        other = self._mk_user('p_other', 'myschool_projects.group_projects_user')
        proj = self.P.create({'name': 'Hidden', 'responsible_id': other.id})
        # see-all ziet + bewerkt ondanks geen membership
        self.assertTrue(self.P.with_user(seer).search([('id', '=', proj.id)]))
        proj.with_user(seer).write({'name': 'seen'})

    def test_access_task_follows_project(self):
        owner = self._mk_user('p_to', 'myschool_projects.group_projects_user')
        reader = self._mk_user('p_tr', 'myschool_projects.group_projects_user')
        proj = self.P.create({'name': 'P', 'responsible_id': owner.id})
        self.env['myschool.project.membership'].create({
            'project_id': proj.id, 'user_id': reader.id, 'role': 'reader'})
        task = self.T.create({'name': 't', 'project_id': proj.id})
        # reader leest de taak maar mag niet bewerken
        self.assertTrue(task.with_user(reader).read(['name']))
        with self.assertRaises(AccessError):
            task.with_user(reader).write({'name': 'x'})
        # owner mag wel
        task.with_user(owner).write({'name': 'ok'})

    # ---------------- delete-cascade ----------------

    def test_delete_task_cascades_subtasks(self):
        proj = self.P.create({'name': 'P'})
        parent = self.T.create({'name': 'parent', 'project_id': proj.id, 'item_type': 'phase'})
        child = self.T.create({'name': 'child', 'project_id': proj.id, 'parent_id': parent.id})
        parent.unlink()
        self.assertFalse(child.exists())

    def test_delete_project_cascades_tasks(self):
        proj = self.P.create({'name': 'P'})
        t = self.T.create({'name': 't', 'project_id': proj.id})
        proj.unlink()
        self.assertFalse(t.exists())

    # ---------------- archiveren ----------------

    def test_archive_project_cascades(self):
        proj = self.P.create({'name': 'P'})
        sub = self.P.create({'name': 'Sub', 'parent_id': proj.id})
        t = self.T.create({'name': 't', 'project_id': proj.id})
        st = self.T.create({'name': 'st', 'project_id': sub.id})
        proj.active = False
        for rec in (sub, t, st):
            rec.invalidate_recordset(['active'])
            self.assertFalse(rec.active)
        # de-archiveren cascadeert ook terug
        proj.active = True
        for rec in (sub, t, st):
            rec.invalidate_recordset(['active'])
            self.assertTrue(rec.active)

    def test_archive_task_cascades_subtasks(self):
        proj = self.P.create({'name': 'P'})
        parent = self.T.create({'name': 'p', 'project_id': proj.id, 'item_type': 'phase'})
        child = self.T.create({'name': 'c', 'project_id': proj.id, 'parent_id': parent.id})
        parent.active = False
        child.invalidate_recordset(['active'])
        self.assertFalse(child.active)

    # ---------------- taaktemplates ----------------

    def test_task_template_apply(self):
        Tmpl = self.env['myschool.project.task.template']
        root = Tmpl.create({'name': 'Onboarding', 'item_type': 'phase'})
        Tmpl.create({'name': 'Step 1', 'parent_id': root.id})
        Tmpl.create({'name': 'Step 2', 'parent_id': root.id, 'priority': '2'})
        proj = self.P.create({'name': 'P'})
        task = root.instantiate(proj)
        self.assertEqual(task.project_id, proj)
        self.assertEqual(task.name, 'Onboarding')
        self.assertEqual(len(task.child_ids), 2)
        self.assertEqual(task.child_ids.mapped('project_id'), proj)
        self.assertIn('2', task.child_ids.mapped('priority'))

    def test_save_task_as_template(self):
        proj = self.P.create({'name': 'P'})
        parent = self.T.create({'name': 'Block', 'project_id': proj.id, 'item_type': 'phase'})
        self.T.create({'name': 'sub', 'project_id': proj.id, 'parent_id': parent.id})
        action = parent.action_save_as_task_template()
        tmpl = self.env['myschool.project.task.template'].browse(action['res_id'])
        self.assertEqual(tmpl.name, 'Block')
        self.assertEqual(len(tmpl.child_ids), 1)
        self.assertEqual(tmpl.child_ids.name, 'sub')

    # ---------------- proces invoegen ----------------

    def _build_process(self, state='approved'):
        """Bouw een proces: start → A(task) → G(gateway) → B(task) →
        S(subprocess) → end, met de flow via connecties."""
        Proc = self.env['myschool.process']
        Step = self.env['myschool.process.step']
        Conn = self.env['myschool.process.connection']
        proc = Proc.create({'name': 'Aanwervingsproces',
                            'description': 'demo', 'state': state})
        s = {
            'start': Step.create({'name': 'Start', 'step_type': 'start', 'map_id': proc.id}),
            'A': Step.create({'name': 'Vacature opstellen', 'step_type': 'task',
                              'description': 'opstellen', 'map_id': proc.id}),
            'G': Step.create({'name': 'Akkoord?', 'step_type': 'gateway_exclusive',
                              'map_id': proc.id}),
            'B': Step.create({'name': 'Publiceren', 'step_type': 'task', 'map_id': proc.id}),
            'S': Step.create({'name': 'Selectie', 'step_type': 'subprocess', 'map_id': proc.id}),
            'end': Step.create({'name': 'Einde', 'step_type': 'end', 'map_id': proc.id}),
        }
        flow = [('start', 'A'), ('A', 'G'), ('G', 'B'), ('B', 'S'), ('S', 'end')]
        for src, tgt in flow:
            Conn.create({'map_id': proc.id, 'source_step_id': s[src].id,
                         'target_step_id': s[tgt].id})
        return proc

    def test_apply_process_inserts_phase_with_steps(self):
        proc = self._build_process()
        proj = self.P.create({'name': 'P'})
        phase = proj.apply_process(proc)
        # Container = phase met de procesnaam
        self.assertEqual(phase.item_type, 'phase')
        self.assertEqual(phase.name, 'Aanwervingsproces')
        self.assertEqual(phase.project_id, proj)
        # Enkel task/subprocess-stappen worden work items (start/gateway/end niet)
        names = phase.child_ids.mapped('name')
        self.assertEqual(set(names), {'Vacature opstellen', 'Publiceren', 'Selectie'})
        # subprocess → phase, gewone stap → task
        selectie = phase.child_ids.filtered(lambda t: t.name == 'Selectie')
        self.assertEqual(selectie.item_type, 'phase')
        vacature = phase.child_ids.filtered(lambda t: t.name == 'Vacature opstellen')
        self.assertEqual(vacature.item_type, 'task')

    def test_apply_process_order_and_dependencies(self):
        proc = self._build_process()
        proj = self.P.create({'name': 'P'})
        phase = proj.apply_process(proc)
        ordered = phase.child_ids.sorted('sequence')
        # Flow-volgorde: A → B → S (gateway doorgeknipt)
        self.assertEqual(ordered.mapped('name'),
                         ['Vacature opstellen', 'Publiceren', 'Selectie'])
        vac, pub, sel = ordered[0], ordered[1], ordered[2]
        # B(Publiceren) hangt af van A(Vacature) — gateway tussenin doorgeknipt
        self.assertEqual(pub.depends_on_ids, vac)
        # S(Selectie) hangt af van B(Publiceren)
        self.assertEqual(sel.depends_on_ids, pub)
        # A heeft geen voorganger (start telt niet mee)
        self.assertFalse(vac.depends_on_ids)

    def test_apply_process_under_parent(self):
        proc = self._build_process()
        proj = self.P.create({'name': 'P'})
        anchor = self.T.create({'name': 'Fase 1', 'project_id': proj.id, 'item_type': 'phase'})
        phase = proj.apply_process(proc, parent_id=anchor.id)
        self.assertEqual(phase.parent_id, anchor)

    def test_apply_process_allows_unapproved(self):
        # De status-gating zit in de wizard (checkbox); apply_process zelf
        # voegt elk meegegeven proces in — ook een niet-goedgekeurd.
        proc = self._build_process(state='draft')
        proj = self.P.create({'name': 'P'})
        phase = proj.apply_process(proc)
        self.assertEqual(phase.item_type, 'phase')
        self.assertEqual(len(phase.child_ids), 3)
