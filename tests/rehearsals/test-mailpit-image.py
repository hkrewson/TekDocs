"""Exercise SMTP capture and SQLite persistence using a disposable Mailpit image."""
import json
import os
import smtplib
import subprocess
import time
import urllib.request
import uuid

image = os.environ.get('MAILPIT_TEST_IMAGE', 'tekdocs-mailpit-security')
name = 'tekdocs-mailpit-check-' + uuid.uuid4().hex[:12]
volume = name + '-data'


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def start(selected_image=image):
    docker('run', '-d', '--name', name, '-p', '127.0.0.1::1025', '-p', '127.0.0.1::8025',
           '-e', 'MP_DATABASE=/data/mailpit.db', '-v', volume + ':/data', selected_image)
    port = docker('port', name, '8025/tcp').rsplit(':', 1)[1]
    base = 'http://127.0.0.1:' + port
    for _ in range(60):
        try:
            with urllib.request.urlopen(base + '/readyz', timeout=2) as response:
                if response.status == 200:
                    return base
        except OSError:
            # A starting container may refuse HTTP; retry within the bounded loop.
            # Exhaustion below fails the rehearsal rather than accepting unreadiness.
            pass
        time.sleep(0.5)
    raise RuntimeError('Mailpit did not become ready')


def message_count(base):
    with urllib.request.urlopen(base + '/api/v1/messages', timeout=3) as response:
        return json.load(response)['total']


docker('volume', 'create', volume)
try:
    base = start(os.environ.get('MAILPIT_PREVIOUS_IMAGE', image))
    assert message_count(base) == 0
    smtp_port = int(docker('port', name, '1025/tcp').rsplit(':', 1)[1])
    with smtplib.SMTP('127.0.0.1', smtp_port, timeout=5) as smtp:
        smtp.sendmail('sender@example.invalid', ['recipient@example.invalid'],
                      'From: sender@example.invalid\r\nTo: recipient@example.invalid\r\n'
                      'Subject: Synthetic TekDocs persistence check\r\n\r\nSynthetic content.\r\n')
    for _ in range(20):
        if message_count(base) == 1:
            break
        time.sleep(0.25)
    assert message_count(base) == 1, 'SMTP message was not captured'
    docker('stop', name)
    docker('rm', name)
    base = start()
    assert message_count(base) == 1, 'Captured message did not survive restart'
    print('Mailpit SMTP capture, HTTP readiness and SQLite restart persistence passed.')
finally:
    subprocess.run(['docker', 'rm', '-f', name], check=False, stdout=subprocess.DEVNULL)
    subprocess.run(['docker', 'volume', 'rm', volume], check=True, stdout=subprocess.DEVNULL)
