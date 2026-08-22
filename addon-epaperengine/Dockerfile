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

COPY *.py push.mjs probe.mjs /opt/epaperengine/
COPY templates/ /opt/epaperengine/templates/
COPY fonts/ /opt/epaperengine/fonts/
COPY run.sh /run.sh

# The script faces for the guest view (FSD §8.4). They ship *with the add-on*
# rather than coming from apk: no Alpine package carries a script face, and
# downloading them at build time would make a build that runs on the Home
# Assistant host depend on somebody else's server. All three are SIL OFL; the
# licence files sit next to them and are copied along.
#
# Installed into the system font path **and** kept under /opt: Chromium finds
# them through fontconfig by family name, while Pillow opens the very same file
# from /opt to measure how wide a name is (``guest_layout.py``). Two consumers,
# one set of bytes — a font Chromium draws that Pillow never measured is exactly
# the mismatch that would push a greeting off the edge of the panel.
RUN mkdir -p /usr/share/fonts/epaperengine \
 && cp /opt/epaperengine/fonts/*.ttf /usr/share/fonts/epaperengine/ \
 && (fc-cache -f || echo "no fc-cache — fontconfig builds its own at runtime") \
 && chmod a+x /run.sh

CMD [ "/run.sh" ]
