"""Exercise refresh/cache/redirect behavior against the actual Nginx image.

Run through make test-frontend-routing; the disposable container has no data volumes.
"""
import http.client
import os
import re
import subprocess
import time
import unittest


class FrontendRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        image = os.environ.get('TEKDOCS_ROUTING_IMAGE', 'tekdocs-frontend-routing-check')
        cls.container = subprocess.check_output([
            'docker', 'run', '--rm', '-d', '-p', '127.0.0.1::8080',
            '--add-host', 'tekdocs-backend:127.0.0.1', image,
        ], text=True).strip()
        cls.addClassCleanup(subprocess.run, ['docker', 'rm', '-f', cls.container],
                            check=True, stdout=subprocess.DEVNULL)
        address = subprocess.check_output(
            ['docker', 'port', cls.container, '8080'], text=True).strip()
        cls.port = int(address.rsplit(':', 1)[1])
        for _ in range(50):
            try:
                if cls.request('/healthz')[0] == 200:
                    break
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(.1)
        else:
            raise RuntimeError('Isolated frontend did not become ready')

    @classmethod
    def request(cls, path, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', cls.port, timeout=5)
        try:
            connection.request('GET', path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_refresh_preserves_public_origin_and_serves_entry_document(self):
        index = self.request('/index.html')[2]
        for headers in ({'Host': 'localhost:3200'},
                        {'Host': 'docs.example.invalid', 'X-Forwarded-Proto': 'https'}):
            for path in ('/assets', '/assets/', '/assets?preview=synthetic&section=network',
                         '/organizations/synthetic/assets', '/networks'):
                with self.subTest(path=path, headers=headers):
                    status, response_headers, body = self.request(path, headers)
                    self.assertEqual(status, 200)
                    self.assertNotIn('Location', response_headers)
                    self.assertEqual(body, index)
                    self.assertIn('no-cache', response_headers.get('Cache-Control', ''))
                    self.assertIn('Content-Security-Policy', response_headers)

    def test_hashed_files_keep_cache_and_missing_chunks_do_not_return_html(self):
        index = self.request('/index.html')[2].decode()
        path = re.search(r'src="(/assets/[^\"]+\.js)"', index).group(1)
        status, headers, body = self.request(path)
        self.assertEqual(status, 200)
        self.assertIn('javascript', headers['Content-Type'])
        self.assertIn('max-age=31536000', headers['Cache-Control'])
        self.assertTrue(body)
        status, _, body = self.request('/assets/nonexistent-routing-check.js')
        self.assertEqual(status, 404)
        self.assertNotEqual(body, index.encode())

    def test_pdf_worker_has_module_mime_type_and_preserves_asset_headers(self):
        assets = subprocess.check_output([
            'docker', 'exec', self.container, 'ls', '/usr/share/nginx/html/assets',
        ], text=True).splitlines()
        workers = [name for name in assets if name.startswith('pdf.worker.') and name.endswith('.mjs')]
        self.assertEqual(len(workers), 1)
        stylesheet = next(name for name in assets if name.endswith('.css'))
        for name, mime in ((workers[0], 'javascript'), (stylesheet, 'text/css')):
            with self.subTest(asset=name):
                status, headers, body = self.request('/assets/' + name)
                self.assertEqual(status, 200)
                self.assertIn(mime, headers['Content-Type'])
                self.assertIn('max-age=31536000', headers['Cache-Control'])
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                self.assertIn('Content-Security-Policy', headers)
                self.assertTrue(body)
        self.assertEqual(self.request('/assets/nonexistent-pdf-worker.mjs')[0], 404)

    def test_nginx_directory_redirect_is_relative(self):
        subprocess.run(['docker', 'exec', self.container, 'mkdir', '-p',
                        '/usr/share/nginx/html/routing-probe'], check=True)
        status, headers, _ = self.request('/routing-probe', {
            'Host': 'docs.example.invalid', 'X-Forwarded-Proto': 'https'})
        self.assertEqual(status, 301)
        self.assertEqual(headers.get('Location'), '/routing-probe/')


if __name__ == '__main__':
    unittest.main()
