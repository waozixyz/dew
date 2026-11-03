"""Small stdlib CDP client; owns only its private Xvfb and Chromium processes."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
from urllib.request import urlopen
from urllib.request import Request
from urllib.error import HTTPError
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = next((parent for parent in ROOT.parents if (parent / 'harness/waozi/account').is_dir()),
                ROOT.parents[2])


class Browser:
    def __enter__(self):
        scratch = ROOT / 'work/web-test'
        scratch.mkdir(parents=True, exist_ok=True)
        self.profile = Path(tempfile.mkdtemp(prefix='b-', dir=scratch))
        env = {key: value for key, value in os.environ.items() if key not in
               {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER'}}
        # Chromium's temporary Unix socket paths have a short kernel limit.
        env.update(YUE_DESKTOP_RECOVERY='0', TMPDIR=str(ROOT / 'work'))
        self.log = (self.profile / 'chromium.log').open('w+')
        self.process = subprocess.Popen([
            'xvfb-run', '-a', '--server-args=-screen 0 1280x900x24 -nolisten tcp',
            os.environ.get('CHROMIUM') or shutil.which('chromium') or 'google-chrome', '--headless=new', '--no-sandbox',
            '--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--disable-dev-shm-usage',
            '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
            '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--mute-audio',
            '--remote-debugging-port=0', f'--user-data-dir={self.profile}', 'about:blank'],
            env=env, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log, start_new_session=True)
        self.ws = None
        self.sequence = 0
        self.events = []
        self.responses = {}
        self.request_handler = None
        self.referral_replies = []
        self.api_paths = []
        self.api_statuses = []
        try:
            self.wait(lambda: (self.profile / 'DevToolsActivePort').exists(), 30, 'Chromium start')
            port = (self.profile / 'DevToolsActivePort').read_text().splitlines()[0]
            with urlopen(f'http://127.0.0.1:{port}/json/list', timeout=5) as response:
                targets = json.load(response)
            address = urlsplit(next(target['webSocketDebuggerUrl'] for target in targets if target['type'] == 'page'))
            self.ws = socket.create_connection((address.hostname, address.port), timeout=15)
            key = base64.b64encode(os.urandom(16)).decode()
            self.ws.sendall((f'GET {address.path} HTTP/1.1\r\nHost: {address.netloc}\r\n'
                             f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                             'Sec-WebSocket-Version: 13\r\n\r\n').encode())
            headers = bytearray()
            while not headers.endswith(b'\r\n\r\n'):
                headers.extend(self._read(1))
                if len(headers) > 16384:
                    raise RuntimeError('Oversized WebSocket handshake')
            expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
            assert b' 101 ' in headers and expected in headers, 'CDP WebSocket handshake refused'
            self.command('Runtime.enable')
            self.command('Page.enable')
            self.command('Emulation.setDeviceMetricsOverride', {
                'width': 1280, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _read(self, length):
        data = bytearray()
        while len(data) < length:
            part = self.ws.recv(length - len(data))
            if not part:
                raise RuntimeError('CDP socket closed')
            data.extend(part)
        return bytes(data)

    def _send(self, payload, opcode=1):
        mask = os.urandom(4)
        count = len(payload)
        header = bytes([0x80 | opcode, 0x80 | (count if count < 126 else 126 if count < 65536 else 127)])
        if count >= 65536:
            header += struct.pack('!Q', count)
        elif count >= 126:
            header += struct.pack('!H', count)
        self.ws.sendall(header + mask + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)))

    def _receive(self):
        fragments = bytearray()
        while True:
            first, second = self._read(2)
            count = second & 127
            if count == 126:
                count = struct.unpack('!H', self._read(2))[0]
            elif count == 127:
                count = struct.unpack('!Q', self._read(8))[0]
            if count > 4 * 1024 * 1024:
                raise RuntimeError('CDP frame exceeds test limit')
            mask = self._read(4) if second & 128 else None
            payload = self._read(count)
            if mask:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            opcode = first & 15
            if opcode == 9:
                self._send(payload, 10)
                continue
            if opcode == 8:
                raise RuntimeError('CDP closed WebSocket')
            fragments.extend(payload)
            if first & 128:
                return json.loads(fragments)

    def command(self, method, params=None):
        self.sequence += 1
        serial = self.sequence
        self._send(json.dumps({'id': serial, 'method': method, 'params': params or {}}).encode())
        while True:
            if serial in self.responses:
                result = self.responses.pop(serial)
                if 'error' in result:
                    raise RuntimeError(f'{method}: {result["error"]}')
                return result.get('result', {})
            result = self._receive()
            if 'id' in result:
                self.responses[result['id']] = result
                continue
            if result.get('method') == 'Fetch.requestPaused' and self.request_handler:
                self.request_handler(result['params'])
            if result.get('method') in {'Runtime.consoleAPICalled', 'Runtime.exceptionThrown'}:
                self.events = (self.events + [result])[-30:]

    def route_api(self, origin):
        """Route real product API requests to a disposable Daochi HTTP fixture.

        This changes only test transport. Entity still signs its normal auth
        handshake, and the local server still validates it and owns all credits.
        """
        self.route_origins({'https://api.waozi.xyz': origin})

    def route_origins(self, origins):
        """Keep secure product origins while serving only local test fixtures."""
        assert all(urlsplit(value).hostname == '127.0.0.1' for value in origins.values())

        def handle(event):
            request = event['request']
            source = urlsplit(request['url'])
            origin = origins.get(source.scheme + '://' + source.netloc)
            if origin is None:
                self.command('Fetch.failRequest', {'requestId': event['requestId'], 'errorReason': 'BlockedByClient'})
                return
            headers = {key: value for key, value in request['headers'].items()
                       if key.lower() not in {'host', 'content-length'}}
            body = request.get('postData')
            forwarded = Request(origin.rstrip('/') + source.path + ('?' + source.query if source.query else ''),
                                data=body.encode() if body is not None else None,
                                headers=headers, method=request['method'])
            try:
                response = urlopen(forwarded, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                # Generated Wasm is larger than JSON. Keep both explicitly
                # bounded, and never print binary response bodies.
                limit = 1024 * 1024 if source.hostname == 'api.waozi.xyz' else 32 * 1024 * 1024
                payload = response.read(limit + 1)
                assert len(payload) <= limit, 'fixture response exceeds test bound'
                if source.hostname == 'api.waozi.xyz':
                    self.api_paths.append((request['method'], source.path))
                    self.api_statuses.append((request['method'], source.path, response.status))
                    if source.path.startswith('/api/v1/referrals/') and request['method'] != 'OPTIONS':
                        self.referral_replies.append({'path': source.path, 'status': response.status,
                                                     'body': json.loads(payload) if payload else {}})
                response_headers = [{'name': key, 'value': value} for key, value in response.headers.items()
                                    if key.lower() not in {'transfer-encoding', 'content-length', 'content-encoding'}]
                self.command('Fetch.fulfillRequest', {'requestId': event['requestId'],
                             'responseCode': response.status, 'responseHeaders': response_headers,
                             'body': base64.b64encode(payload).decode()})
        self.request_handler = handle
        self.command('Fetch.enable', {'patterns': [{'urlPattern': 'https://*.waozi.xyz/*', 'requestStage': 'Request'}]})

    def evaluate(self, expression, await_promise=False):
        response = self.command('Runtime.evaluate', {
            'expression': expression, 'returnByValue': True, 'awaitPromise': await_promise})
        if 'exceptionDetails' in response:
            raise RuntimeError(str(response['exceptionDetails']))
        return response.get('result', {}).get('value')

    def navigate(self, url):
        self.command('Page.navigate', {'url': url})
        self.wait(lambda: self.evaluate('location.href') == url and self.evaluate('document.readyState') == 'complete', 30, 'page load')

    @staticmethod
    def wait(callback, seconds=15, label='condition'):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = callback()
            if value:
                return value
            time.sleep(.05)
        raise AssertionError(f'Timed out waiting for {label}')

    def click(self, x, y):
        for kind in ['mouseMoved', 'mousePressed', 'mouseReleased']:
            self.command('Input.dispatchMouseEvent', {
                'type': kind, 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
            time.sleep(.08)

    def __exit__(self, *unused):
        if self.ws:
            try:
                self.command('Browser.close')
            except (OSError, RuntimeError):
                pass
            self.ws.close()
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if self.process.poll() is None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.log.close()
        for attempt in range(20):
            try:
                shutil.rmtree(self.profile)
                break
            except FileNotFoundError:
                break
            except OSError:
                if attempt == 19:
                    raise
                time.sleep(.1)
