# Explicit base image on purpose: since Supervisor 2026.04.0 the BUILD_FROM
# argument is no longer provided by default, so a Dockerfile that relies on it
# fails to build.
FROM ghcr.io/home-assistant/base:latest

# This one layer is what turns a 69 MiB image into roughly 790 MiB. It is first
# and it is a single RUN so that Docker caches it: everything after this line
# rebuilds in seconds, which is the whole reason the build stays on the Home
# Assistant host instead of going through CI [Festlegung 2026-08-21].
#
# Sizes measured on ha-test1 with ``apk add --simulate`` (Alpine 3.24.1):
#   base image                            68.7 MiB
#   + py3-pillow, py3-jinja2, DejaVu      88.8 MiB
#   + chromium-headless-shell            703.1 MiB
#   + nodejs, npm                        ~772   MiB
#
# ``chromium-headless-shell`` and **not** ``chromium``: the full package adds a
# second 282 MB browser binary that nothing here would ever launch. The headless
# shell alone produces the exact 2560×1440 screenshot in 1.11 s [measured].
#
# Only DejaVu is installed. FSD §7's type sizes were measured at the panel with
# DejaVu Sans; adding Noto now would grow the image for a font no template asks
# for yet.
#
# ``samsung-mdc`` goes into a *local* node_modules, not a global one: push.mjs is
# an ES module, and ESM resolution ignores NODE_PATH — a globally installed
# package would simply not be found. Pinned, because it speaks a protocol.
RUN apk add --no-cache \
        python3 py3-aiohttp py3-pillow py3-jinja2 \
        chromium-headless-shell \
        font-dejavu \
        nodejs npm \
 && npm install --prefix /opt/epaperengine --no-fund --no-audit \
        @weejewel/samsung-mdc@1.0.1 \
 && npm cache clean --force \
 && rm -rf /root/.npm /tmp/*

COPY *.py push.mjs /opt/epaperengine/
COPY templates/ /opt/epaperengine/templates/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
