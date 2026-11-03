# Dew

[dew.waozi.xyz](https://dew.waozi.xyz) is one focused page for topping up
Dew, the currency every Waozi app shares: Inner Breeze, Arcade, Shovey,
Apfelwurm and the rest. You sign in with the same profile those apps
use, see your balance, and pay:

- **Monero, any amount.** Each account has its own Monero address on the
  Waozi node. Whatever arrives there becomes Dew at the node's rate
  (10,000 Dew = 1 XMR today) once it has the node's confirmations.
- **Almost any other coin, from 100 Dew.** The page opens
  [Trocador AnonPay](https://trocador.app/anonpay/) in payment mode with
  the account's address and the exact Monero amount. Trocador swaps the
  payer's coin and sends that Monero to the address; the node credits it
  like any Monero payment. Trocador swaps no less than 0.01 XMR, so the
  page asks for at least that much.

The page never grants Dew. The node sets the rate and credits deposits;
the page reads the balance and address through Entity's shared Profile,
whose provider is the only code that touches account keys.

## Referrals

`https://dew.waozi.xyz/invite/CODE` prefills an invitation in Entity's shared
**My referrals** page. `?ref=CODE` and manual code entry work too. Landing on
a link never binds an account: sign in, review the code and disclosure, then explicitly
confirm. Daochi binds the account and credits the once-only 20 Dew welcome
gift together, immediately, without a purchase or minimum spend. The UI
confirms a gift only after the server returns its receipt.

My referrals uses the same Entity account and signed provider as other apps.
It shows the server-issued sharing code/link, aggregate earnings and paginated
accepted friends, including people who never bought Dew. The inviter sees
each friend's public name/alias or account ID and acceptance date; that
disclosure appears before acceptance. Invitations are unlimited, and the
inviter earns 5% in Dew on the friend's paid purchases on an ongoing basis.
Each account can have only one inviter across participating apps.

An unaccepted code is kept in the URL and this tab's session storage across
reloads and sign-in. There is no claim timer or automatic acceptance. Keep
the displayed code to enter manually if installation or another device loses
the link. Dismiss link removes the tab's suggestion; the shared UI lets you edit
its saved manual code. Private account keys,
binding policy, balances, receipts and the accepted list stay with Entity and
the authoritative Daochi service; the web shell stores none of those.

`/referrals` opens the dashboard. The canonical waozi.xyz and
account.waozi.xyz `/invite/CODE`, `/invite` and `/referrals` routes forward
to Dew while retaining the query. Optional `app` and `platform` hints travel
with the pending code. Direct/web/desktop/F-Droid invitations use this flow.
Play, Apple, Amazon and unknown platform hints open only the referral/profile
flow: valid signed-in welcome claims remain available, while web top-up and
payment controls stay disabled. For paid Dew the user returns to the originating
app's payment options. A source hint never proves store provenance or chooses
a credit allocation; the server owns those decisions.

The integration uses `EntityHostReferrals(code)` (prefill only), not a second
web identity/signing implementation. Entity's `entity.referrals` service
calls Daochi's authenticated `/api/v1/referrals/me`, `/claim` and
`/accepted?cursor=…&limit=50` endpoints. Account changes discard old results.

## Build

Dependencies use `ziran.toml` and `ziran.lock`; local overrides belong in
the ignored `ziran.local.toml`. The browser build needs Emscripten.

```sh
build-queue -- make test       # model tests + offline referral landing browser tests
build-queue -- make web        # the whole site in build/web
build-queue -- make web-test   # generated site in Chromium on private Xvfb
make serve      # http://127.0.0.1:8095
```

`src/topup.zi` draws the page with Kryon widgets, `src/topup_model.zi` holds
the arithmetic and links, and `src/web/runtime.zi` is the browser host. The
site shell is in `site/`; `design/og.svg` is the source of `site/og.jpg`.
`src/web/referral.js` owns only pending-code attribution and platform routing.
The Python stdlib CDP harness in `tests/browser.py` needs Chromium and Xvfb,
uses a disposable profile under ignored `work/web-test`, scrubs inherited
display/session variables, disables desktop recovery and touches only its own
processes. No Node is used by the browser tests. The Emscripten web builder
also supports an existing Bun runtime through
`EM_NODE_JS=/absolute/path/to/bun`. Set that variable in sessions that prohibit
Node; it selects Bun directly, without a Node shim.

`python3 tests/referral_integration_test.py` additionally uses Daochi's compiled
test-only `work/referral-fixture.test`. It starts and stops a disposable local
server, creates real accounts through Entity, and tests explicit acceptance,
the immediate server receipt without a purchase, accepted nonpurchasers,
pagination, public-ID fallback and switching accounts through the real shared
account hub. Its private fixture report and logs stay under ignored
`work/referral`; browser traffic never reaches production.

## Releases

Releases start in `CHANGELOG.md` and `./update_version.sh`. A push to master
builds and tests the site, and a new numeric version is published as a
GitHub release carrying `dew-web-vX.Y.Z.zip`. The waozi.xyz repository
deploys the latest release to dew.waozi.xyz by itself.
