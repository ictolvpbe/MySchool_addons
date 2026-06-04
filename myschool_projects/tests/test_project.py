from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError
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
