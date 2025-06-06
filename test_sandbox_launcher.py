import unittest
from pathlib import Path
import sandbox_launcher as sl

class TestMerkleHash(unittest.TestCase):
    def test_merkle_hash_changes_when_file_changes(self):
        with open('tmpfile', 'w') as f:
            f.write('a')
        h1 = sl.merkle_hash(Path('.'))
        with open('tmpfile', 'w') as f:
            f.write('b')
        h2 = sl.merkle_hash(Path('.'))
        self.assertNotEqual(h1, h2)
        Path('tmpfile').unlink()

class TestDockerCmd(unittest.TestCase):
    def test_build_docker_cmd_contains_security_flags(self):
        cmd = sl.build_docker_cmd('img', [Path('/tmp')], ['bash'], 'dev')
        joined = ' '.join(cmd)
        self.assertIn('--network none', joined)
        self.assertIn('--read-only', joined)
        self.assertIn('--runtime=runsc', joined)
        self.assertIn('--user dev', joined)

class TestPrepareOverlays(unittest.TestCase):
    def test_prepare_overlays_creates_isolated_copy(self):
        orig = Path('orig')
        orig.mkdir(exist_ok=True)
        (orig / 'file.txt').write_text('hello')
        mapping = sl.prepare_overlays([orig])
        overlay = mapping[orig]
        self.assertTrue((overlay / 'file.txt').exists())
        (overlay / 'file.txt').write_text('changed')
        self.assertEqual((orig / 'file.txt').read_text(), 'hello')
        sl.cleanup_overlays(mapping)
        for p in [orig]:
            for child in p.iterdir():
                child.unlink()
            p.rmdir()


class TestSnapshots(unittest.TestCase):
    def test_diff_snapshots_detects_changes(self):
        d = Path('snap')
        d.mkdir(exist_ok=True)
        f = d / 'file.txt'
        f.write_text('one')
        initial = sl.snapshot_directories([d])
        f.write_text('two')
        final = sl.snapshot_directories([d])
        diff = sl.diff_snapshots(initial, final)
        self.assertIn('snap', diff)
        self.assertTrue(any('Modified: file.txt' in s for s in diff['snap']))
        f.unlink()
        d.rmdir()

if __name__ == '__main__':
    unittest.main()
