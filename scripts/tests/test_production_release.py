from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ProductionReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'checkout'
        self.root.mkdir()
        for name in ('scripts/update-production.sh', 'scripts/lib/production-images.sh',
                     'scripts/lib/production-release.sh', 'scripts/releases/v0.9.8.images'):
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)
        (self.root / '.gitignore').write_text('.env\n.tekdocs-update.env\n')
        (self.root / 'VERSION').write_text('0.9.8\n')
        for name in ('compose.yml', 'compose.production.yml', 'compose.secret-files.yml',
                     'compose.images.yml', 'compose.traefik.yml'):
            (self.root / name).write_text('services: {}\n')
        backup = self.root / 'scripts/tekdocs-backup.sh'
        backup.write_text('#!/bin/sh\necho backup >> "$TEST_EVENTS"\n[ -z "${TEST_BACKUP_FAIL:-}" ]\n')
        backup.chmod(0o755)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic release test')
        self.git('config', 'user.email', 'release@example.invalid')
        self.git('add', '.')
        self.git('commit', '-qm', 'release fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.git('tag', 'v0.9.8')
        # Receipt/tooling intentionally follow the immutable application tag.
        receipt = self.root / 'scripts/releases/v0.9.8.images'
        receipt.write_text(receipt.read_text().replace(
            '05abb130625ae875c58253e309ba6821ee89ed66', self.commit))
        self.git('add', '.')
        self.git('commit', '-qm', 'release receipt')
        self.tooling_commit = self.git('rev-parse', 'HEAD').strip()
        self.git('remote', 'add', 'origin', str(self.root))
        # This fixture stores only the directory path in .env, never key material.
        self.deployment_directory = Path(self.temp.name) / 'deployment-files'
        self.deployment_directory.mkdir()
        self.key = Path(self.temp.name) / 'recovery-key'
        self.key.write_bytes(os.urandom(32))
        (self.root / '.env').write_text(
            f'TEKDOCS_SECRET_DIRECTORY={self.deployment_directory}\nTEKDOCS_PUBLIC_URL=https://docs.example.invalid\n')
        self.events = Path(self.temp.name) / 'events'
        bindir = Path(self.temp.name) / 'bin'
        bindir.mkdir()
        docker = bindir / 'docker'
        docker.write_text('''#!/usr/bin/env python3
import os,sys,json
args=sys.argv[1:]
with open(os.environ['TEST_EVENTS'],'a') as f: f.write(json.dumps(args)+'\\n')
if args[0]=='compose':
 if 'ps' in args and '-q' in args: print('synthetic-'+args[-1])
 if 'run' in args and 'migrate' in args and os.environ.get('TEST_MIGRATION_FAIL'): sys.exit(17)
elif args[0]=='inspect':
 if 'org.opencontainers.image.revision' in args[2]: print(os.environ['TEST_RUNNING_COMMIT'])
 else:
  receipt=dict(line.strip().split('=',1) for line in open(os.environ['TEST_RECEIPT']))
  service=args[-1].removeprefix('synthetic-')
  key={'frontend':'frontend','diagram-renderer':'renderer','mailpit':'mailpit'}.get(service,'backend')
  print('wrong-image' if os.environ.get('TEST_WRONG_RUNNING_IMAGE') else receipt[key])
elif args[:2]==['image','inspect']:
 if 'org.opencontainers.image.revision' in args[3]:
  print('0'*40 if os.environ.get('TEST_BAD_REVISION') or (os.environ.get('TEST_BAD_MAILPIT_REVISION') and 'tekdocs-mailpit' in args[-1]) else os.environ['TEST_RELEASE_COMMIT'])
 else:
  repo=args[-1].split(':')[0]
  receipt=dict(line.strip().split('=',1) for line in open(os.environ['TEST_RECEIPT']))
  name={'tekdocs-backend':'backend','tekdocs-frontend':'frontend','tekdocs-diagram-renderer':'renderer','tekdocs-mailpit':'mailpit'}[repo.rsplit('/',1)[1]]
  print(repo+'@sha256:'+'0'*64 if os.environ.get('TEST_BAD_DIGEST') or (os.environ.get('TEST_BAD_MAILPIT_DIGEST') and name=='mailpit') else receipt[name])
elif args[0]!='pull': sys.exit(9)
''')
        docker.chmod(0o755)
        curl = bindir / 'curl'
        curl.write_text('#!/bin/sh\nexit 0\n')
        curl.chmod(0o755)
        self.env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'],
                        TEST_EVENTS=str(self.events), TEST_RELEASE_COMMIT=self.commit,
                        TEST_RUNNING_COMMIT=self.commit, TEST_RECEIPT=str(receipt))
        self.before_env = (self.root / '.env').read_text()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True, stderr=subprocess.PIPE)

    def run_update(self, release='v0.9.8'):
        return subprocess.run(['bash', 'scripts/update-production.sh', *(['--release', release] if release is not None else []),
                               '--backup-root', str(Path(self.temp.name)/'backups'),
                               '--recovery-key', str(self.key)], cwd=self.root, env=self.env,
                              text=True, capture_output=True)

    def enable_mailpit_release(self):
        (self.root / 'compose.images.yml').write_text('services: {}\n# TEKDOCS_MAILPIT_IMAGE\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'four-image application fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.git('tag', '-f', 'v0.9.8')
        receipt = self.root / 'scripts/releases/v0.9.8.images'
        lines = receipt.read_text().splitlines()
        lines[0] = 'commit=' + self.commit
        lines.append('mailpit=ghcr.io/hkrewson/tekdocs-mailpit@sha256:' + 'a' * 64)
        receipt.write_text('\n'.join(lines) + '\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'four-image receipt fixture')
        self.env.update(TEST_RELEASE_COMMIT=self.commit, TEST_RUNNING_COMMIT=self.commit)

    def enable_remote_receipt(self):
        self.enable_mailpit_release()
        self.git('tag', 'receipts/v0.9.8')
        saved = Path(self.temp.name) / 'verified.images'
        shutil.copyfile(self.root / 'scripts/releases/v0.9.8.images', saved)
        self.env['TEST_RECEIPT'] = str(saved)
        self.git('rm', 'scripts/releases/v0.9.8.images')
        self.git('commit', '-qm', 'tooling without local receipt')

    def test_ci_receipt_is_fetched_without_changing_checkout(self):
        self.enable_remote_receipt()
        before = self.git('rev-parse', 'HEAD')
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), before)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertIn('TEKDOCS_MAILPIT_IMAGE=', (self.root / '.env').read_text())

    def test_ci_receipt_with_wrong_parent_is_rejected_before_backup(self):
        self.enable_remote_receipt()
        self.git('tag', '-f', 'receipts/v0.9.8')
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.events.exists())

    def test_missing_ci_receipt_is_rejected_before_backup(self):
        self.enable_remote_receipt()
        self.git('tag', '-d', 'receipts/v0.9.8')
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.events.exists())

    def test_four_image_release_verifies_and_persists_mailpit(self):
        self.enable_mailpit_release()
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('TEKDOCS_MAILPIT_IMAGE=ghcr.io/hkrewson/tekdocs-mailpit@sha256:',
                      (self.root / '.env').read_text())
        self.assertIn('synthetic-mailpit', self.events.read_text())

    def test_four_image_release_rejects_missing_mailpit_receipt_before_stop(self):
        self.enable_mailpit_release()
        receipt = self.root / 'scripts/releases/v0.9.8.images'
        receipt.write_text('\n'.join(line for line in receipt.read_text().splitlines()
                                    if not line.startswith('mailpit=')) + '\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'missing mailpit receipt fixture')
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires a reviewed Mailpit digest', result.stderr)
        self.assert_no_stop()

    def test_four_image_release_rejects_wrong_mailpit_identity_before_stop(self):
        self.enable_mailpit_release()
        for flag in ('TEST_BAD_MAILPIT_REVISION', 'TEST_BAD_MAILPIT_DIGEST'):
            with self.subTest(flag=flag):
                self.env[flag] = '1'
                result = self.run_update()
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_stop()
                self.env.pop(flag)

    def test_four_image_receipt_rejects_duplicate_mailpit(self):
        self.enable_mailpit_release()
        receipt = self.root / 'scripts/releases/v0.9.8.images'
        receipt.write_text(receipt.read_text() + receipt.read_text().splitlines()[-1] + '\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'duplicate mailpit fixture')
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_stop()

    def assert_no_stop(self):
        events = self.events.read_text() if self.events.exists() else ''
        self.assertNotIn('"stop"', events)
        self.assertEqual((self.root / '.env').read_text(), self.before_env)

    def test_release_uses_exact_images_snapshot_and_preserves_tooling_checkout(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.events.read_text().splitlines()
        self.assertEqual(events.count('backup'), 1)
        self.assertLess(events.index('backup'), next(i for i, line in enumerate(events) if '"pull"' in line))
        calls = [json.loads(line) for line in events if line != 'backup']
        pulls = [call[1] for call in calls if call[0] == 'pull']
        self.assertEqual(len(pulls), 3)
        self.assertTrue(all(p.endswith(':sha-'+self.commit) for p in pulls))
        stop = next(c for c in calls if 'stop' in c)
        self.assertIn(str(self.root), stop)
        snapshot = next(c for c in stop if c.endswith('/compose.yml'))
        self.assertNotEqual(snapshot, str(self.root/'compose.yml'))
        self.assertFalse(Path(snapshot).exists(), 'temporary snapshot must be cleaned')
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), self.tooling_commit)
        self.assertIn('TEKDOCS_DEPLOYED_COMMIT='+self.commit, (self.root/'.env').read_text())
        self.assertIn('TEKDOCS_RENDERER_IMAGE=ghcr.io/', (self.root/'.env').read_text())

    def test_wrong_digest_and_revision_never_stop_application(self):
        for flag in ('TEST_BAD_DIGEST', 'TEST_BAD_REVISION'):
            with self.subTest(flag=flag):
                self.env[flag] = '1'
                result = self.run_update()
                del self.env[flag]
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_stop()

    def test_backup_and_migration_failures_do_not_record_success(self):
        for flag in ('TEST_BACKUP_FAIL', 'TEST_MIGRATION_FAIL'):
            with self.subTest(flag=flag):
                self.env[flag] = '1'
                result = self.run_update()
                del self.env[flag]
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.root / '.env').read_text(), self.before_env)
                if flag == 'TEST_BACKUP_FAIL':
                    self.assert_no_stop()
                    self.assertNotIn('"pull"', self.events.read_text())

    def test_existing_upstream_mode_is_preserved(self):
        branch = self.git('branch', '--show-current').strip()
        self.git('config', f'branch.{branch}.remote', 'origin')
        self.git('config', f'branch.{branch}.merge', f'refs/heads/{branch}')
        self.git('fetch', 'origin', branch)
        self.env['TEST_RELEASE_COMMIT'] = self.tooling_commit
        result = self.run_update(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.events.read_text().splitlines() if line != 'backup']
        pulls = [call[1] for call in calls if call[0] == 'pull']
        self.assertEqual(len(pulls), 3)
        self.assertTrue(all(p.endswith(':sha-'+self.tooling_commit) for p in pulls))

    def test_wrong_running_image_does_not_record_success(self):
        self.env['TEST_WRONG_RUNNING_IMAGE'] = '1'
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('running service does not use', result.stderr)
        self.assertEqual((self.root / '.env').read_text(), self.before_env)

    def test_rejects_missing_or_unsafe_release(self):
        for release in ('v9.9.9', '../../main', '--all', 'main', ''):
            with self.subTest(release=release):
                self.assertNotEqual(self.run_update(release).returncode, 0)
                self.assert_no_stop()

    def test_tag_mismatch_and_backward_runtime_are_rejected(self):
        self.env['TEST_RUNNING_COMMIT'] = self.tooling_commit
        self.assertNotEqual(self.run_update().returncode, 0)
        self.assert_no_stop()
        self.env['TEST_RUNNING_COMMIT'] = self.commit
        self.git('tag', '-f', 'v0.9.8', self.tooling_commit)
        self.assertNotEqual(self.run_update().returncode, 0)
        self.assert_no_stop()


if __name__ == '__main__':
    unittest.main()
