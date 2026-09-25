import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from deployment_rehearsal import copy_persistent, owned_checkpoints


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
