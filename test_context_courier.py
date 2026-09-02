import tempfile
import unittest
from pathlib import Path

from context_courier import buildSnapshot


class SnapshotFilteringTests(unittest.TestCase):
    def test_snapshot_respects_gitignore_patterns_and_negation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            project = temporary_path / "project"
            snapshot = temporary_path / "snapshot"
            project.mkdir()
            (project / ".gitignore").write_text(
                "cache/\n*.db\nconfig.json\nignored/*\n!ignored/keep.txt\n",
                encoding="utf-8",
            )
            files = {
                "app.py": "source",
                "config.json": "local",
                "cache/thumbnail.webp": "generated",
                "database/local.db": "runtime",
                "database/schema.py": "source",
                "ignored/drop.txt": "ignored",
                "ignored/keep.txt": "kept",
            }
            for relative_path, contents in files.items():
                path = project / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding="utf-8")

            buildSnapshot(project, snapshot)

            copied = {
                path.relative_to(snapshot).as_posix()
                for path in snapshot.rglob("*")
                if path.is_file()
            }
            self.assertEqual(
                copied,
                {
                    ".gitignore",
                    "app.py",
                    "database/schema.py",
                    "ignored/keep.txt",
                },
            )

    def test_snapshot_keeps_unignored_files_without_gitignore(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            project = temporary_path / "project"
            snapshot = temporary_path / "snapshot"
            project.mkdir()
            (project / "source.txt").write_text("source", encoding="utf-8")

            buildSnapshot(project, snapshot)

            self.assertEqual(
                (snapshot / "source.txt").read_text(encoding="utf-8"),
                "source",
            )


if __name__ == "__main__":
    unittest.main()
