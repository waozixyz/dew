#!/usr/bin/env python3
"""Real generated UI + shared account hub + Daochi ML-DSA/referral HTTP routes.

Requires the backend worker's compiled, test-only referral browser fixture.
Every account and browser profile is disposable; no production traffic occurs.
"""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from urllib.request import Request, urlopen

from browser import Browser, PROJECTS, ROOT
from web_site_test import Handler, driver

BACKEND = PROJECTS / 'kryonlabs/daochi'


@contextmanager
def fixture():
    scratch = ROOT / 'work/referral'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fixture-', dir=scratch) as directory:
        report = Path(directory) / 'report.json'
        log = (scratch / 'integration-server.log').open('w+')
        env = {key: value for key, value in os.environ.items() if key not in
               {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER'}}
        env.update(DAOCHI_REFERRAL_FIXTURE_REPORT=str(report), YUE_DESKTOP_RECOVERY='0', TMPDIR=directory)
        binary = Path(os.environ.get('DAOCHI_REFERRAL_FIXTURE_BIN', BACKEND / 'work/referral-fixture.test'))
        process = subprocess.Popen([str(binary),
                                    '-test.run', '^TestReferralBrowserFixture$', '-test.v', '-test.timeout=10m'],
                                   cwd=BACKEND, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=log, start_new_session=True)
        metadata = None
        try:
            Browser.wait(report.exists, 30, 'real-auth fixture startup')
            metadata = json.loads(report.read_text())
            assert metadata['synthetic'] and metadata['real_mldsa']
            assert metadata['authority'] == 'https://api.waozi.xyz'

            def control(path, body=None):
                request = Request(metadata['url'] + '/fixture/' + path,
                                  data=json.dumps(body or {}).encode(), method='POST',
                                  headers={'X-Fixture-Key': metadata['control_key'], 'Content-Type': 'application/json'})
                with urlopen(request, timeout=20) as response:
                    return json.load(response)

            yield metadata['url'], control
        finally:
            if metadata:
                try:
                    control('stop')
                except OSError:
                    pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            log.close()
            if process.returncode:
                raise RuntimeError(f'Referral fixture exited with {process.returncode}; see {log.name}')


def tree(browser):
    return driver(browser, 'tree')['nodes']


def click_widget(browser, key):
    for attempt in range(24):
        nodes = driver(browser, 'find\tkey=' + str(key))['nodes']
        if not nodes:
            if attempt >= 3:
                browser.command('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': 850, 'y': 700})
                browser.command('Input.dispatchMouseEvent', {'type': 'mouseWheel', 'x': 850, 'y': 700,
                                                           'deltaX': 0, 'deltaY': 650})
            time.sleep(.1)
            continue
        node = nodes[0]
        if node['enabled'] and node['visible'] and node['visible_height'] > 10:
            browser.click(node['visible_x'] + node['visible_width'] / 2,
                          node['visible_y'] + node['visible_height'] / 2)
            return
        direction = 1 if node['y'] > 450 else -1
        browser.command('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': 850, 'y': 700})
        browser.command('Input.dispatchMouseEvent', {'type': 'mouseWheel', 'x': 850, 'y': 700,
                                                   'deltaX': 0, 'deltaY': direction * 650})
        time.sleep(.1)
    labels = [node['label'] for node in tree(browser) if node['visible']]
    raise AssertionError(f'Widget {key} unavailable; visible labels: {labels}')


def ready(browser):
    Browser.wait(lambda: browser.evaluate('!!(window.Module && Module.profileReady && Module.profileVisible)'),
                 90, 'generated referral UI')


def fill_code(browser, value):
    click_widget(browser, 107)
    browser.command('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Control', 'code': 'ControlLeft',
                                             'windowsVirtualKeyCode': 17, 'modifiers': 2})
    browser.command('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'a', 'code': 'KeyA',
                                             'windowsVirtualKeyCode': 65, 'modifiers': 2})
    time.sleep(.15)
    browser.command('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'a', 'code': 'KeyA',
                                             'windowsVirtualKeyCode': 65, 'modifiers': 2})
    browser.command('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Control', 'code': 'ControlLeft',
                                             'windowsVirtualKeyCode': 17})
    time.sleep(.1)
    for character in value:
        browser.command('Input.dispatchKeyEvent', {'type': 'char', 'text': character, 'key': character})
    try:
        Browser.wait(lambda: any(node['key'] == 107 and node['value'] == value for node in tree(browser)),
                     10, 'manual code edit')
    except AssertionError:
        raise AssertionError('Manual code edit state: ' + json.dumps([node for node in tree(browser)
                                                                    if node['key'] == 107])) from None


def wait_api(browser, predicate, label):
    # CDP requests must keep being pumped while waiting for intercepted HTTP.
    try:
        Browser.wait(lambda: browser.evaluate('true') and predicate(), 30, label)
    except AssertionError as error:
        observed = [(reply['path'], reply['status'], reply['body'].get('error', ''))
                    for reply in browser.referral_replies]
        labels = [node['label'] for node in tree(browser) if node['visible']]
        raise AssertionError(f'{error}; API: {observed}; requests: {browser.api_statuses}; UI: {labels}') from None


def create_account(browser):
    click_widget(browser, 78005)
    click_widget(browser, 820)
    Browser.wait(lambda: browser.evaluate('!!(Module.sharedAccountOwner && Module.sharedAccountOwner.length === 64)'),
                 30, 'actual account creation and hub handoff')
    owner = browser.evaluate('Module.sharedAccountOwner')
    # Opaque fixture account material from the real provider is retained only
    # inside this test process, never printed, decoded or used to sign anything.
    key = browser.evaluate('Module.sharedAccountKey')
    for _ in range(4):
        if any(node['key'] == 78003 for node in tree(browser)):
            break
        browser.click(54, 28)
        time.sleep(.15)
    wait_api(browser, lambda: any(reply['path'].endswith('/me') and reply['status'] == 200 and
                                reply['body'].get('account_id') == owner for reply in browser.referral_replies),
             'signed referral summary')
    return owner, key


def switch_shared_account(browser, owner, key):
    previous = browser.evaluate('performance.timeOrigin')
    browser.evaluate('void WaoziAccount.share(' + json.dumps(key) + ', ' + json.dumps(owner) + ', false); true')
    Browser.wait(lambda: browser.evaluate('performance.timeOrigin') != previous, 20, 'actual shared-account reload')
    ready(browser)
    Browser.wait(lambda: browser.evaluate('Module.sharedAccountOwner') == owner, 15, 'shared account selection')


def integration(browser, control):
    browser.navigate('https://dew.waozi.xyz/referrals')
    ready(browser)
    inviter, inviter_key = create_account(browser)
    seeded = control('seed', {'account_id': inviter, 'count': 51})
    code = seeded['code']
    click_widget(browser, 78009)
    Browser.wait(lambda: 'fixture-referral-049' in json.dumps(tree(browser)), 30, 'accepted nonpurchasers first page')
    first_page = tree(browser)
    assert 'fixture-referral-000' in json.dumps(first_page)
    assert any(node['key'] == 78101 and node['label'] for node in first_page), 'acceptance date missing'
    click_widget(browser, 78027)
    Browser.wait(lambda: 'fixture-referral-050' in json.dumps(tree(browser)), 30, 'accepted next page')
    assert 'fixture-referral-000' not in json.dumps(tree(browser)), 'pagination retained stale page'
    print('Local integration: real signup, signed summary and nonpurchaser pagination passed', flush=True)

    # Sign out through the real account UI, then create a fresh account.
    browser.click(54, 28)
    click_widget(browser, 830)
    click_widget(browser, 8808)
    Browser.wait(lambda: browser.evaluate('!Module.sharedAccountOwner'), 20, 'actual sign-out')
    browser.navigate('https://dew.waozi.xyz/invite/' + code + '?platform=play&app=shovey')
    ready(browser)
    friend, friend_key = create_account(browser)
    assert friend != inviter
    assert 'fixture-referral-' not in json.dumps(tree(browser)), 'previous account referrals leaked'
    assert not any(reply['path'].endswith('/claim') for reply in browser.referral_replies), 'landing silently claimed'
    fill_code(browser, 'BAD_MANUAL')
    print('Local integration: fresh friend account and manual code edit passed', flush=True)
    saved = browser.evaluate("['referral-pending.txt','referral-suggestion.txt'].map(name => { try { return Module.FS.readFile('/kryon-apps/profile/' + name, {encoding:'utf8'}); } catch (_) { return 'missing'; } })")
    assert saved == ['BAD_MANUAL', code], 'Shared referral files before reload: ' + json.dumps(saved)
    browser.evaluate('new Promise((resolve,reject) => Module.FS.syncfs(false, error => error ? reject(error) : resolve(true)))', True)
    previous = browser.evaluate('performance.timeOrigin')
    browser.command('Page.reload')
    Browser.wait(lambda: browser.evaluate('performance.timeOrigin') != previous, 15, 'safe reload')
    ready(browser)
    try:
        Browser.wait(lambda: any(node['key'] == 107 and node['value'] == 'BAD_MANUAL' for node in tree(browser)),
                     30, 'manual code survives reload over URL suggestion')
    except AssertionError:
        fields = [node for node in tree(browser) if node['key'] == 107]
        raise AssertionError('Manual reload state: ' + json.dumps(fields)) from None
    print('Local integration: manual code survived generated-app reload', flush=True)
    fill_code(browser, code)
    click_widget(browser, 78024)
    assert not any(reply['path'].endswith('/claim') for reply in browser.referral_replies), 'review silently claimed'
    click_widget(browser, 78022)
    wait_api(browser, lambda: any(reply['path'].endswith('/claim') and reply['status'] == 200
                                for reply in browser.referral_replies), 'authoritative claim receipt')
    claim = next(reply['body'] for reply in browser.referral_replies if reply['path'].endswith('/claim') and reply['status'] == 200)
    assert claim['status'] == 'bound' and claim['welcome_units'] == 20_000_000 and claim['welcome_receipt_id']
    Browser.wait(lambda: any(node['key'] == 78006 for node in tree(browser)), 15, 'immediate welcome gift confirmation')
    assert not any(method == 'POST' and 'purchase' in path for method, path in browser.api_paths), 'welcome gift required a purchase'
    assert not any(node['key'] in {60020, 60030, 60040} for node in tree(browser)), 'store-source claim exposed web payment'

    switch_shared_account(browser, inviter, inviter_key)
    Browser.wait(lambda: 'fixture-referral-049' in json.dumps(tree(browser)), 30, 'restored inviter list')
    click_widget(browser, 78027)
    Browser.wait(lambda: friend in json.dumps(tree(browser)), 30, 'real nonpurchaser public-ID fallback')
    fresh = len(browser.referral_replies)
    switch_shared_account(browser, friend, friend_key)
    wait_api(browser, lambda: any(reply['path'].endswith('/me') and reply['body'].get('account_id') == friend
                                for reply in browser.referral_replies[fresh:] if reply['status'] == 200), 'friend summary after switch')
    wait_api(browser, lambda: any(reply['path'].endswith('/accepted') and reply['body'].get('accepted') == []
                                for reply in browser.referral_replies[fresh:] if reply['status'] == 200), 'friend owner-scoped empty list')
    assert 'fixture-referral-' not in json.dumps(tree(browser)), 'old-owner rows survived shared account switch'
    assert any(node['key'] == 78018 for node in tree(browser)), 'permanent inviter binding not shown after reload'
    assert sum(reply['path'].endswith('/claim') for reply in browser.referral_replies) == 1, 'reload repeated claim'
    print('Local real-auth browser integration passed: explicit signed claim, immediate20 without purchase, nonpurchaser name/date/ID fallback, pagination, shared-account isolation')


def main():
    Handler.site = ROOT / 'build/web'
    Handler.landing_only = False
    Handler.shared_account = True
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with fixture() as (api, control), Browser() as browser:
            local = f'http://127.0.0.1:{server.server_port}'
            browser.route_origins({'https://dew.waozi.xyz': local,
                                   'https://account.waozi.xyz': local + '/__account',
                                   'https://api.waozi.xyz': api})
            integration(browser, control)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
