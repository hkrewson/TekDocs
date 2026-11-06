from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('finalize', ROOT / 'scripts/finalize_ci_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
REAL_SUBPROCESS_RUN = subprocess.run
SHA = 'a' * 40
DIGEST = 'sha256:' + 'b' * 64


class FinalizeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        old = Path.cwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, old)
        Path('VERSION').write_text('0.9.12\n')
        tag_messages = Path('planning/releases/tag-messages')
        tag_messages.mkdir(parents=True)
        (tag_messages / 'v0.9.12.txt').write_text(
            'Synthetic release for delivery tests\nBreaking changes: none\n')
        env = dict(GITHUB_SHA=SHA, GITHUB_REF='refs/heads/main', GITHUB_EVENT_NAME='push',
                   GITHUB_REPOSITORY='hkrewson/TekDocs', GITHUB_SERVER_URL='https://github.com',
                   GITHUB_RUN_ID='123', GITHUB_STEP_SUMMARY=str(Path.cwd() / 'summary'))
        env.update({name.upper() + '_DIGEST': DIGEST for name in release.IMAGES})
        self.enterContext(patch.dict(os.environ, env))
        self.calls = []
        self.bad_signature = False
        self.tag_sha = ''
        self.tag_commit_sha = ''
        self.receipt_sha = ''
        self.receipt_text = ''
        self.enterContext(patch.object(release, 'run', side_effect=self.command))
        self.alias = self.enterContext(patch.object(release.subprocess, 'run', return_value=
            subprocess.CompletedProcess([], 1, '', 'manifest unknown')))

    def command(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ('gh', 'attestation'):
            if self.bad_signature:
                raise subprocess.CalledProcessError(1, args)
            return '[{"verified":true}]'
        if args[:4] == ('docker', 'buildx', 'imagetools', 'inspect'):
            return json.dumps(DIGEST)
        if args[:3] == ('git', 'ls-remote', '--tags'):
            if 'receipts/' in args[-1]:
                value = self.receipt_sha
            elif args[-1].endswith('^{}'):
                value = self.tag_commit_sha
            else:
                value = self.tag_sha
            return value + '\t' + args[-1] if value else ''
        if args[:2] == ('git', 'show'):
            return self.receipt_text.strip()
        if args[:2] == ('git', 'rev-parse'):
            return SHA
        return 'c' * 40

    def test_verified_release_atomically_pushes_both_tags(self):
        release.finalize()
        checks = [c for c in self.calls if c[:2] == ('gh', 'attestation')]
        self.assertEqual(len(checks), 8)
        self.assertTrue(all('--source-digest' in c and '--source-ref' in c for c in checks))
        pushes = [c for c in self.calls if c[:2] == ('git', 'push')]
        self.assertEqual(len(pushes), 1)
        self.assertIn('--atomic', pushes[0])
        self.assertTrue(any(ref.endswith(':refs/tags/v0.9.12') for ref in pushes[0]))
        self.assertTrue(any(c[:2] == ('git', 'mktag') for c in self.calls))
        self.assertTrue(pushes[0][-1].endswith(':refs/tags/receipts/v0.9.12'))
        self.assertEqual(len(Path('artifacts/release/v0.9.12.images').read_text().splitlines()), 5)

    def test_failed_signature_delivers_no_tags_or_version_aliases(self):
        self.bad_signature = True
        with self.assertRaises(subprocess.CalledProcessError):
            release.finalize()
        self.assertFalse(any(c[:2] in [('git', 'push'), ('docker', 'push')] for c in self.calls))

    def test_existing_release_for_other_commit_is_rejected(self):
        self.tag_sha = 'd' * 40
        with self.assertRaises(ValueError):
            release.finalize()
        self.assertFalse(any(c[0] == 'docker' for c in self.calls))

    def test_matching_annotated_release_is_accepted_without_rewriting_tag(self):
        self.tag_sha = 'd' * 40
        self.tag_commit_sha = SHA
        release.finalize()
        push = next(c for c in self.calls if c[:2] == ('git', 'push'))
        self.assertIn(self.tag_sha + ':refs/tags/v0.9.12', push)
        self.assertFalse(any(c[:2] == ('git', 'mktag') for c in self.calls))

    def test_missing_reviewed_tag_message_stops_before_publication(self):
        Path('planning/releases/tag-messages/v0.9.12.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing reviewed release tag message'):
            release.finalize()
        self.assertFalse(any(c[0] in {'docker', 'gh'} for c in self.calls))

    def test_tag_message_requires_explicit_breaking_change_line(self):
        Path('planning/releases/tag-messages/v0.9.12.txt').write_text(
            'Synthetic release for delivery tests\nNo operator action\n')
        with self.assertRaisesRegex(ValueError, 'explicitly describe breaking changes'):
            release.finalize()
        self.assertFalse(any(c[0] in {'docker', 'gh'} for c in self.calls))

    def test_mismatched_existing_alias_is_never_overwritten(self):
        self.alias.return_value = subprocess.CompletedProcess([], 0, json.dumps('sha256:' + 'e'*64), '')
        with self.assertRaises(ValueError):
            release.finalize()
        self.assertFalse(any(c[:2] == ('docker', 'push') for c in self.calls))

    def test_registry_error_is_not_treated_as_absent_alias(self):
        self.alias.return_value = subprocess.CompletedProcess([], 1, '', 'unauthorized')
        with self.assertRaises(ValueError):
            release.finalize()
        self.assertFalse(any(c[:2] == ('git', 'push') for c in self.calls))

    def test_matching_retry_preserves_receipt_commit(self):
        self.tag_sha = SHA
        self.receipt_sha = 'f' * 40
        self.receipt_text = 'commit=' + SHA + '\n' + ''.join(
            name + '=ghcr.io/hkrewson/' + image + '@' + DIGEST + '\n'
            for name, image in release.IMAGES.items())
        release.finalize()
        pushes = [c for c in self.calls if c[:2] == ('git', 'push')]
        self.assertEqual(pushes[0][-1], self.receipt_sha + ':refs/tags/receipts/v0.9.12')
        self.assertFalse(any(c[:2] == ('git', 'commit-tree') for c in self.calls))

    def test_real_git_delivery_and_retry_keep_source_branch_unchanged(self):
        # Exercise real Git objects and an atomic push to a disposable local remote.
        self.alias.side_effect = lambda args, **kwargs: (REAL_SUBPROCESS_RUN(args, **kwargs)
            if args[0] == 'git' else subprocess.CompletedProcess(args, 1, '', 'manifest unknown'))
        def git(*args):
            return subprocess.check_output(['git', *args], text=True).strip()
        git('init', '-q')
        git('config', 'user.name', 'Synthetic Release Test')
        git('config', 'user.email', 'release@example.invalid')
        git('add', 'VERSION')
        git('add', 'planning/releases/tag-messages/v0.9.12.txt')
        git('commit', '-qm', 'synthetic application')
        sha = git('rev-parse', 'HEAD')
        remote = Path(self.temp.name) / 'remote.git'
        git('init', '--bare', '-q', str(remote))
        git('remote', 'add', 'origin', str(remote))
        def command(*args, **kwargs):
            if args[0] == 'git':
                return subprocess.check_output(args, text=True, **kwargs).strip()
            return self.command(*args, **kwargs)
        with patch.dict(os.environ, GITHUB_SHA=sha), patch.object(release, 'run', side_effect=command):
            release.finalize()
            first = git('ls-remote', '--tags', 'origin')
            tag_object = git('ls-remote', '--tags', 'origin', 'refs/tags/v0.9.12').split()[0]
            self.assertEqual(git('rev-parse', tag_object + '^{}'), sha)
            self.assertIn('Breaking changes: none', git('cat-file', '-p', tag_object))
            release.finalize()
            self.assertEqual(git('ls-remote', '--tags', 'origin'), first)
        self.assertEqual(git('rev-parse', 'HEAD'), sha)
        git('fetch', '-q', 'origin', 'refs/tags/receipts/v0.9.12')
        self.assertEqual(git('rev-parse', 'FETCH_HEAD^'), sha)
        self.assertEqual(git('diff-tree', '--no-commit-id', '--name-only', '-r', 'FETCH_HEAD'),
                         'scripts/releases/v0.9.12.images')

    def test_workflow_requires_all_release_dependencies_and_receipt_step(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        version_check = (ROOT / 'scripts/check-version.sh').read_text()
        self.assertIn('needs: [prepare, production-containers, release-codeql, release-extended]', workflow)
        self.assertNotIn('tags: ["v*"]', workflow)
        self.assertIn('run: python3 scripts/finalize_ci_release.py', workflow)
        self.assertIn('application_commit=${peeled:-$existing}', workflow)
        self.assertIn('refs/tags/v$VERSION^{}', workflow)
        self.assertIn('make test-release-delivery', workflow)
        self.assertIn('uses: ./.github/workflows/codeql.yml', workflow)
        self.assertIn('uses: ./.github/workflows/extended-validation.yml', workflow)
        self.assertIn('name: build-playwright-chromium-summary', workflow)
        self.assertIn('--validate-tag-message', version_check)

    def test_commit_image_rebuild_conflict_is_never_pushed(self):
        self.alias.return_value = subprocess.CompletedProcess([], 0,
            json.dumps({'config': {'digest': 'sha256:' + 'e'*64}}), '')
        with self.assertRaises(ValueError):
            release.publish_commit_images()
        self.assertFalse(any(c[:2] == ('docker', 'push') for c in self.calls))

    def test_missing_commit_images_are_published(self):
        release.publish_commit_images()
        self.assertEqual(len([c for c in self.calls if c[:2] == ('docker', 'push')]), 4)

    def test_pr_cannot_finalize(self):
        with patch.dict(os.environ, GITHUB_EVENT_NAME='pull_request'):
            with self.assertRaises(ValueError):
                release.finalize()
        self.assertFalse(self.calls)


if __name__ == '__main__':
    unittest.main()
