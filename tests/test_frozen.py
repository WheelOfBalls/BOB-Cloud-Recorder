# Every sha256 listed in the FROZEN_*.md tables must match the file it names, so a frozen file cannot change
# without the table changing in the same commit. Run: python3 -m unittest discover -s tests
import os, re, hashlib, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ROW = re.compile(r"^\|\s*`([^`]+)`[^|]*\|\s*`([0-9a-f]{64})`", re.M)


def sha(path):
    with open(os.path.join(ROOT, path), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Frozen(unittest.TestCase):
    def check(self, table):
        with open(os.path.join(ROOT, table), encoding="utf-8") as f:
            rows = ROW.findall(f.read())
        self.assertGreaterEqual(len(rows), 3, table)
        for path, h in rows:
            with self.subTest(table=table, path=path):
                self.assertEqual(sha(path), h, f"{path} changed but {table} was not updated")

    def test_stage2(self):
        self.check("analysis/FROZEN_stage2.md")

    def test_stage3(self):
        self.check("analysis/FROZEN_stage3.md")


if __name__ == "__main__":
    unittest.main()
