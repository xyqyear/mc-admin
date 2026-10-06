import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deployment_rehearsal import Deployment, copy_persistent, owned_checkpoints


class CandidateTaskTests(unittest.TestCase):
    def deployment(self, replies):
        deployment = Deployment.__new__(Deployment)
        deployment.server = "owned"
        calls = []
        responses = iter(replies)

        def request(method, path, data=None, **kwargs):
            calls.append((method, path, data, kwargs))
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response

        deployment.request = request
        return deployment, calls

    def test_acceptance_and_running_progress_do_not_complete_the_task(self):
        for snapshot in (False, True):
            with self.subTest(snapshot=snapshot):
                result = {"snapshot": {"id": "snapshot-id"}, "history": "retained"}
                deployment, calls = self.deployment([
                    {"task_id": "task-id"}, {"status": "pending"},
                    {"status": "running", "progress": 100},
                    {"status": "completed", "result": result},
                ])
                with patch("deployment_rehearsal.time.monotonic", return_value=10), patch("deployment_rehearsal.time.sleep") as sleep:
                    actual = deployment.snapshot_task() if snapshot else deployment.task("/recovery", {"input": "owned"})
                self.assertEqual(actual, "snapshot-id" if snapshot else result)
                self.assertEqual(calls[0][0], "POST")
                self.assertEqual(calls[0][3], {"expected": 202})
                self.assertEqual([call[:2] for call in calls[1:]], [("GET", "/tasks/task-id")] * 3)
                self.assertEqual([call.args for call in sleep.call_args_list], [(0.2,), (0.2,)])

    def test_failed_and_cancelled_keep_distinct_operation_labels(self):
        for snapshot in (False, True):
            for status in ("failed", "cancelled"):
                with self.subTest(snapshot=snapshot, status=status):
                    deployment, _ = self.deployment([{"task_id": "task-id"}, {"status": status}])
                    with (
                        patch("deployment_rehearsal.time.monotonic", return_value=10),
                        self.assertRaisesRegex(AssertionError, "^Candidate " + ("snapshot" if snapshot else "recovery") + " task failed$"),
                    ):
                        deployment.snapshot_task() if snapshot else deployment.task("/recovery")

    def test_deadline_starts_after_acceptance_with_existing_budgets(self):
        for snapshot, budget in ((False, 120), (True, 180)):
            with self.subTest(snapshot=snapshot):
                deployment, calls = self.deployment([{"task_id": "task-id"}])
                samples = iter((10, 10 + budget))

                def monotonic(calls=calls, samples=samples):
                    self.assertEqual(len(calls), 1)
                    return next(samples)

                with (
                    patch("deployment_rehearsal.time.monotonic", side_effect=monotonic),
                    self.assertRaisesRegex(AssertionError, "^Candidate " + ("snapshot" if snapshot else "recovery") + " task did not finish$"),
                ):
                    deployment.snapshot_task() if snapshot else deployment.task("/recovery")
                self.assertEqual(len(calls), 1)

    def test_request_and_missing_fields_propagate_at_the_original_phase(self):
        for replies, exception, phase in (
            ([RuntimeError("acceptance")], RuntimeError, 1),
            ([{}, {"status": "completed"}], KeyError, 1),
            ([{"task_id": "task-id"}, RuntimeError("observation")], RuntimeError, 2),
            ([{"task_id": "task-id"}, {}], KeyError, 2),
            ([{"task_id": "task-id"}, {"status": "completed"}], KeyError, 2),
        ):
            with self.subTest(replies=replies):
                deployment, calls = self.deployment(replies)
                with patch("deployment_rehearsal.time.monotonic", return_value=10), self.assertRaises(exception):
                    deployment.task("/recovery")
                self.assertEqual(len(calls), phase)


class CheckpointOwnershipTests(unittest.TestCase):
    def test_failed_stop_retains_checkpoint_inside_owned_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def failed_stop():
                raise RuntimeError("writer stop unconfirmed")

            deployment = SimpleNamespace(root=root, stop=failed_stop)
            retained = []
            with self.assertRaisesRegex(RuntimeError, "writer stop unconfirmed"), owned_checkpoints(deployment) as checkpoint:
                retained.append(checkpoint)
                (checkpoint / "new-data").write_text("retain me")
            self.assertEqual((retained[0] / "new-data").read_text(), "retain me")
            self.assertEqual(retained[0].parent, root)

    def test_full_copy_excludes_its_own_storage_and_drains_before_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "servers").mkdir()
            (root / "servers" / "new-data").write_text("durable bytes")
            (root / "db.sqlite3").write_bytes(b"closed database fixture")
            stopped = []

            def stopped_writer():
                self.assertTrue((checkpoint / "released" / "db.sqlite3").is_file())
                stopped.append(True)

            deployment = SimpleNamespace(root=root, stop=stopped_writer)
            with owned_checkpoints(deployment) as checkpoint:
                copy_persistent(deployment, checkpoint / "released", checkpoint)
                self.assertEqual((checkpoint / "released" / "servers" / "new-data").read_text(), "durable bytes")
                self.assertFalse((checkpoint / "released" / checkpoint.name).exists())
            self.assertEqual(stopped, [True])
            self.assertFalse(checkpoint.exists())
            self.assertEqual((root / "servers" / "new-data").read_text(), "durable bytes")


if __name__ == "__main__":
    unittest.main()
