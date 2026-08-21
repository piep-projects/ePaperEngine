# Explicit base image on purpose: since Supervisor 2026.04.0 the BUILD_FROM
# argument is no longer provided by default, so a Dockerfile that relies on it
# fails to build.
FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-aiohttp

COPY server.py /opt/epaperengine/server.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
