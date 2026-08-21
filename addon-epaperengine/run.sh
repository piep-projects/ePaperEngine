#!/usr/bin/with-contenv sh
# The shebang is the whole point: s6-overlay does NOT hand the container
# environment to a service it starts. It keeps those variables in
# /run/s6/container_environment/, and `with-contenv` is what loads them before
# exec'ing the interpreter. Without it SUPERVISOR_TOKEN is simply empty, every
# call to the Home Assistant API answers 401, and nothing says why.
# [measured 2026-08-21 on the test instance]
set -e
exec python3 /opt/epaperengine/server.py
