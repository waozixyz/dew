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

## Build

Dependencies use `ziran.toml` and `ziran.lock`; local overrides belong in
the ignored `ziran.local.toml`. The browser build needs Emscripten.

```sh
make test       # conversions, minimum and payment links
make web        # the whole site in build/web
make web-test   # opens build/web in a private headless Chromium
make serve      # http://127.0.0.1:8095
```

`src/topup.zi` draws the page with Kryon widgets, `src/topup_model.zi` holds
the arithmetic and links, and `src/web/runtime.zi` is the browser host. The
site shell is in `site/`; `design/og.svg` is the source of `site/og.jpg`.

## Releases

Releases start in `CHANGELOG.md` and `./update_version.sh`. A push to master
builds and tests the site, and a new numeric version is published as a
GitHub release carrying `dew-web-vX.Y.Z.zip`. The waozi.xyz repository
deploys the latest release to dew.waozi.xyz by itself.
