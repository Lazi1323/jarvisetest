import os
import tempfile
import unittest
from pathlib import Path

import jarvis


class FileSearchTests(unittest.TestCase):
    def test_searches_name_and_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.txt").write_text("Jarvis remembers Nobara", encoding="utf-8")
            (root / "jarvis.py").write_text("print('ok')", encoding="utf-8")

            names = jarvis.FileSearch.search("jarvis.py", roots=[tmp], mode="name")
            content = jarvis.FileSearch.search("Nobara", roots=[tmp], mode="content")

            self.assertEqual(names[0][0], str(root / "jarvis.py"))
            self.assertEqual(content[0][0], str(root / "notes.txt"))


class MemoryTests(unittest.TestCase):
    def test_memory_round_trip(self):
        old_db, old_json = jarvis.Config.FILE_MEM_DB, jarvis.Config.FILE_MEM
        with tempfile.TemporaryDirectory() as tmp:
            jarvis.Config.FILE_MEM_DB = os.path.join(tmp, "memory.db")
            jarvis.Config.FILE_MEM = os.path.join(tmp, "memory.json")
            jarvis.MemoryManager.save_memory("использует Nobara", category="preference")
            self.assertIn("использует Nobara", jarvis.MemoryManager.get_memory_context())
            self.assertEqual(jarvis.MemoryManager.forget_memory("Nobara"), 1)
        jarvis.Config.FILE_MEM_DB, jarvis.Config.FILE_MEM = old_db, old_json


class ReminderTests(unittest.TestCase):
    def test_relative_reminder(self):
        title, due_at = jarvis.JarvisGUI._parse_reminder("через 20 минут проверить GPU")
        self.assertEqual(title, "проверить GPU")
        self.assertGreater(due_at, jarvis.time.time())


class PluginTests(unittest.TestCase):
    def test_builtin_plugins_loaded(self):
        self.assertIn("TIME_NOW", jarvis.PluginManager.actions)
        self.assertIn("SYSTEM_STATUS", jarvis.PluginManager.actions)


if __name__ == "__main__":
    unittest.main()
