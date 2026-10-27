ZIRAN ?= ziran
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
TOOLCHAIN = $(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS))
ENTITY = $(shell $(ZIRAN) pkg path entity $(LOCK_FLAGS))
PORT ?= 8095

.PHONY: all test web web-test serve
all: web

test: build/model-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/model-test/test
	$(ZIRAN) fmt --check src/*.zi src/web/*.zi tests/*.zi

build/model-test/test: src/topup_model.zi tests/topup_model_test.zi ziran.lock
	rm -rf build/model-test
	$(ZIRAN) build --project $(LOCK_FLAGS) --target=c --entry topup_model_test:main -o build/model-test tests/topup_model_test.zi
	$(CC) -std=c99 -O2 -I'$(TOOLCHAIN)/include' -Ibuild/model-test $$(find build/model-test -type d -printf ' -iquote %p') \
		$$(find build/model-test -name '*.c') -o $@

# The page and the shared Profile, linked with Entity's account provider.
# build/web is the whole site; version.json names the source it came from.
web:
	$(MAKE) -C '$(ENTITY)' build/entity.zx ZIRAN='$(TOOLCHAIN)/build/bin/ziran'
	rm -rf build/web
	ZIRAN='$(TOOLCHAIN)/build/bin/ziran' python3 '$(ENTITY)/scripts/build-web.py' \
		--profile '$(ENTITY)/build/entity.zx' --output build/web/runtime.html
	rm -f build/web/runtime.html
	cp site/index.html site/_headers site/icon.svg site/manifest.webmanifest site/og.jpg site/icon-512.png site/apple-touch-icon.png build/web/
	printf '{"version":"%s","revision":"%s"}\n' \
		"$$(python3 -c 'import json; print(json.load(open("version.json"))["version"])')" \
		"$$(git rev-parse HEAD)" > build/web/version.json

# Opens the built site in a private headless browser.
web-test:
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS node tests/web_site_test.mjs build/web

serve:
	python3 -m http.server $(PORT) --bind 127.0.0.1 --directory build/web
