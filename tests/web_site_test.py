#!/usr/bin/env python3
"""Exercise actual browser attribution and generated Dew/Entity Wasm without Node."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit

from browser import Browser, PROJECTS, ROOT


class Handler(SimpleHTTPRequestHandler):
    site = ROOT / 'site'
    landing_only = False
    shared_account = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.site), **kwargs)

    def log_message(self, *unused):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/__account/'):
            name = path.removeprefix('/__account/')
            if name == 'hub':
                name = 'hub.html'
            if name not in {'share.js', 'hub.html'}:
                return self.send_error(404)
            public_file = PROJECTS / 'harness/waozi/account' / name
            return self.answer(public_file.read_bytes(), 'text/javascript' if name.endswith('.js') else 'text/html')
        if path == '/referral.js' and self.landing_only:
            return self.answer((ROOT / 'src/web/referral.js').read_bytes(), 'text/javascript')
        if path == '/runtime.js' and self.landing_only:
            return self.answer(b'window.runtimeStarted = (window.runtimeStarted || 0) + 1;', 'text/javascript')
        if path in {'/', '/invite', '/referrals'} or path.startswith('/invite/'):
            page = (self.site / 'index.html').read_text()
            # The test is entirely offline: no production hub/account/network.
            if not self.shared_account:
                page = page.replace("shared.src = 'https://account.waozi.xyz/share.js';",
                                    "shared.src = '/test-share.js';")
            if not self.landing_only:
                page = page.replace('window.Module = {', "window.Module = { preRun: [function () { ENV.KRYON_TEST_DRIVER = '/test'; Module.FS.mkdir('/test'); }],")
            return self.answer(page.encode(), 'text/html')
        if path == '/test-share.js':
            return self.answer(b'window.WaoziAccount = {attach: function () {return Promise.resolve();}};', 'text/javascript')
        return super().do_GET()

    def answer(self, body, content_type):
        self.send_response(200)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/__transport_test':
            return self.send_error(404)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.answer(json.dumps({'received': body.decode()}).encode(), 'application/json')


def landing(browser, origin):
    browser.navigate(origin + '/invite/TEST_CODE?app=shovey&lang=de')
    assert browser.evaluate('DewReferral.code') == 'TEST_CODE'
    assert browser.evaluate('DewReferral.requested') is True
    assert browser.evaluate('document.querySelector("#referral-gift").textContent.includes("sofort 20 Dew")')
    assert browser.evaluate('Module.referralRequested') is True
    browser.navigate(origin + '/?lang=es')
    assert browser.evaluate('DewReferral.code') == 'TEST_CODE', 'code lost across sign-in/reload'
    assert browser.evaluate('DewReferral.sourceApp') == 'shovey'
    assert browser.evaluate('document.querySelector("#referral-manual").textContent.includes("Guarda")')
    browser.navigate(origin + '/?ref=%3Cscript%3E&lang=en')
    assert browser.evaluate('DewReferral.code') == '', 'invalid link must not recover older code'
    assert browser.evaluate('document.querySelector("#referral-manual").textContent.includes("manually")')
    browser.navigate(origin + '/invite/STORE_CODE?platform=gplay&app=shovey')
    assert browser.evaluate('DewReferral.fundingAllowed') is False
    assert browser.evaluate('Module.referralOnly') is True, 'store link opened payment flow'
    assert browser.evaluate('document.querySelector("#referral-code").textContent') == 'STORE_CODE'
    browser.navigate(origin + '/')
    assert browser.evaluate('DewReferral.fundingAllowed') is False, 'reload lost store source restriction'
    assert browser.evaluate('document.querySelector("#referral-open").hidden') is False, 'store hint blocked welcome claim'
    for platform in ['apple', 'amazon', 'unrecognized']:
        browser.navigate(origin + '/invite/STORE_CODE?platform=' + platform)
        assert browser.evaluate('DewReferral.fundingAllowed') is False
    browser.navigate(origin + '/invite/DIRECT_CODE?platform=fdroid&lang=fr')
    assert browser.evaluate('DewReferral.fundingAllowed') is True
    assert browser.evaluate('document.querySelector("#referral-landing").lang') == 'en'
    browser.evaluate('document.querySelector("#referral-forget").click()')
    browser.wait(lambda: browser.evaluate('location.pathname + location.search') == '/?lang=en')
    browser.wait(lambda: browser.evaluate('typeof DewReferral !== "undefined" && DewReferral.code === ""'))
    assert browser.evaluate('DewReferral.requested') is False
    # A privacy-restricted browser still keeps the original link available.
    browser.command('Page.addScriptToEvaluateOnNewDocument', {'source':
        "Storage.prototype.getItem = Storage.prototype.setItem = function () {throw Error('disabled')};"})
    browser.navigate(origin + '/?ref=MANUAL_CODE&view=referrals')
    assert browser.evaluate('DewReferral.code') == 'MANUAL_CODE'
    browser.route_api(origin)
    response = browser.evaluate("fetch('https://api.waozi.xyz/__transport_test', {method:'POST',body:'fixture'}).then(r => r.json())", True)
    assert response == {'received': 'fixture'}, 'local-only API routing changed request bytes'
    print('Local browser tests: link/manual fallback, reload, EN/DE/ES, invalid code, storage denial, source routing passed')


def driver(browser, verb):
    serial = browser.evaluate('(window.testSerial = (window.testSerial || 0) + 1)')
    command = json.dumps(str(serial) + '\t' + verb + '\n')
    browser.evaluate(f'Module.FS.writeFile("/test/next", {command}); Module.FS.rename("/test/next", "/test/command")')
    Browser.wait(lambda: browser.evaluate('Module.FS.analyzePath("/test/reply").exists'), 15, verb)
    response = browser.evaluate('JSON.parse(Module.FS.readFile("/test/reply", {encoding:"utf8"}))')
    browser.evaluate('Module.FS.unlink("/test/reply")')
    assert response['ok'], response
    return response


def generated(browser, origin):
    browser.navigate(origin + '/')
    browser.wait(lambda: browser.evaluate('!!(window.Module && Module.profileReady)'), 90, 'generated app startup')
    assert browser.evaluate('Module.sharedAccountReady') is True, 'actual shared account hub did not complete handoff'
    tree = driver(browser, 'tree')
    assert 'My referrals' in json.dumps(tree), 'topup has no referrals entry'
    button = driver(browser, 'find\tkey=60006')['nodes'][0]
    browser.click(button['x'] + button['width'] / 2, button['y'] + button['height'] / 2)
    browser.wait(lambda: browser.evaluate('!!Module.profileVisible'), 15, 'referrals entry')
    browser.navigate(origin + '/invite/MANUAL_CODE')
    browser.wait(lambda: browser.evaluate('!!(window.Module && Module.profileReady && Module.profileVisible)'), 90, 'referral landing')
    tree = driver(browser, 'tree')
    assert 'My referrals' in json.dumps(tree), 'Entity referral route did not open'
    assert browser.evaluate('Module.referralCode') == 'MANUAL_CODE', 'landing lost prefill'
    assert 'MANUAL_CODE' in json.dumps(tree), 'signed-out flow hides the manual fallback code'
    signin = driver(browser, 'find\tkey=78005')['nodes'][0]
    browser.click(signin['visible_x'] + signin['visible_width'] / 2,
                  signin['visible_y'] + signin['visible_height'] / 2)
    browser.wait(lambda: any(node['key'] == 820 for node in driver(browser, 'tree')['nodes']),
                 10, 'referral sign-in opens actual account choices')
    browser.navigate(origin + '/invite/STORE_CODE?platform=play&app=shovey')
    browser.wait(lambda: browser.evaluate('!!(window.Module && Module.profileReady && Module.profileVisible)'), 90, 'store-source referral route')
    tree = driver(browser, 'tree')
    assert 'STORE_CODE' in json.dumps(tree)
    assert any(node['key'] == 78005 for node in tree['nodes']), 'store hint blocked sign-in/welcome claim'
    assert not any(node['key'] in {60020, 60030, 60040} for node in tree['nodes']), 'store route exposed web purchase'
    for _ in range(2):
        browser.click(54, 28)
        tree = driver(browser, 'tree')
        assert not any(node['key'] in {60020, 60030, 60040} for node in tree['nodes']), 'Back exposed web purchase'
    for locale, title in [('de', 'Meine Empfehlungen'), ('es', 'Mis referidos')]:
        browser.navigate(origin + '/referrals?lang=' + locale)
        browser.wait(lambda: browser.evaluate('!!(window.Module && Module.profileReady && Module.profileVisible)'),
                     90, 'translated shared referrals')
        assert any(node['key'] == 78003 and node['label'] == title for node in driver(browser, 'tree')['nodes'])
    assert 'frame failed' not in json.dumps(browser.events), browser.events
    print('Local generated-app browser tests: Dew entry, shared Entity referral route and landing prefill passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('site', nargs='?', default='build/web', type=Path)
    parser.add_argument('--landing-only', action='store_true')
    args = parser.parse_args()
    Handler.site = ROOT / 'site' if args.landing_only else args.site.resolve()
    Handler.landing_only = args.landing_only
    Handler.shared_account = not args.landing_only
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with Browser() as browser:
            if args.landing_only:
                landing(browser, f'http://127.0.0.1:{server.server_port}')
            else:
                local = f'http://127.0.0.1:{server.server_port}'
                browser.route_origins({'https://dew.waozi.xyz': local,
                                       'https://account.waozi.xyz': local + '/__account'})
                generated(browser, 'https://dew.waozi.xyz')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
