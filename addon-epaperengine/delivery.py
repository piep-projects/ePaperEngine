"""Compare, serve, push, copy (FSD §6.2 steps 6 and 8–9, §10, §11).

The push path deserves a note, because the specification contradicted itself
here and the contradiction was resolved on 2026-08-21 in favour of §10.1/§3.2:

``@weejewel/samsung-emdx``, the tool that proved the protocol on 2026-08-19,
starts an **express server of its own** on a free port from 3000 upwards, serves
``/content.json`` and ``/image`` from there, and calls ``process.exit(0)`` the
moment the display has fetched the image once [read from its source, version
1.0.1]. Port 8099 never appears in it. That is fine for a command-line demo and
wrong for a wall display: the picture is unreachable a second later, so the
device cannot re-fetch, and the port is random rather than the one declared in
``config.yaml``.

So the add-on writes ``content.json`` itself, serves both files from its own
:8099 for as long as it runs, and uses only the protocol layer
``@weejewel/samsung-mdc`` (1.2 MB, its sole dependency is yargs) to say
``set_content_download``. Everything inside the document is byte-for-byte what
the proven tool produced — including the two things nobody would guess: every
``/`` escaped as ``\\/`` over the finished string, and ``file_size`` as a
*string*.
"""

from __future__ import annotations

import hashlib
import json
import logging
import socket
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    # Only for the annotation. Keeping Pillow out of the runtime imports lets the
    # manifest tests of FSD §10.1 run on a bare CI runner, where the shape of
    # ``content.json`` is exactly the thing worth guarding.
    from PIL import Image

_LOGGER = logging.getLogger("epaperengine.delivery")

PUSH_SCRIPT = Path(__file__).parent / "push.mjs"
PROBE_SCRIPT = Path(__file__).parent / "probe.mjs"

# Connect, hand over the URL, disconnect. Generous, because the panel answers
# slowly, but finite so a mute display cannot wedge the queue.
PUSH_TIMEOUT_S = 90

# A probe only reads. It must fail *fast*: it runs behind a sensor that is polled
# on a timer, and behind a button somebody is standing in front of.
PROBE_TIMEOUT_S = 20

# Verbatim from the tool that worked. The original carries a `// TODO ?` next to
# the duration — it is not understood and is taken over unchanged (FSD §10.1).
CONTENT_DURATION = 91326
CONTENT_FILE_PATH = "/home/owner/content/Downloads/vxtplayer/epaper/mobile/contents"

# The one field that differs from the proven document, and only because it is
# the human-readable name of the deployment. If a push ever fails for no visible
# reason, this is the first thing to put back to "node-samsung-emdx".
CONTENT_NAME = "epaperengine"


def fingerprint(image: "Image.Image") -> str:
    """Identity of a rendered picture (FSD §11).

    Over the **pixels**, not over the PNG file. The specification says "PNG
    hash", but two encodes of identical pixels are only byte-identical as long as
    the encoder and its settings never move; hashing what will actually be seen
    removes that dependency, and it is what the rule is about.
    """
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def local_ip_towards(host: str) -> str:
    """The address the display has to fetch from.

    Asked of the routing table rather than of the interface list: with
    ``host_network: true`` the add-on sees every interface of the Home Assistant
    machine, and only the route towards the display says which one it is. No
    packet is sent — a connected UDP socket only fixes the local end.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((host, 9))  # discard port, nothing is transmitted
        return str(probe.getsockname()[0])


def build_content_json(image_url: str, image_size: int, suffix: str = "png") -> bytes:
    """The manifest the display downloads (FSD §10.1).

    ``file_id`` is new on every push [Festlegung A3] — that is what the phone app
    does, and with a fresh UUID the question of whether the panel caches a stable
    one never arises.
    """
    file_id = str(uuid.uuid4()).upper()
    file_name = f"{file_id}.{suffix}"
    document = {
        "schedule": [
            {
                "start_date": "1970-01-01",
                "stop_date": "2999-12-31",
                "start_time": "00:00:00",
                "contents": [
                    {
                        "image_url": image_url,
                        "file_id": file_id,
                        "file_path": f"{CONTENT_FILE_PATH}/{file_id}/{file_name}",
                        "duration": CONTENT_DURATION,
                        # A string, not a number, and it has to be right.
                        "file_size": str(image_size),
                        "file_name": file_name,
                    }
                ],
            }
        ],
        "name": CONTENT_NAME,
        "version": 1,
        "create_time": "2025-01-01 00:00:00",
        "id": file_id,
        # These three claim to be the phone app. The panel believes them.
        "program_id": "com.samsung.ios.ePaper",
        "content_type": "ImageContent",
        "deploy_type": "MOBILE",
    }
    # The blunt replace over the finished string, exactly as the original does
    # it. ``json.dumps`` never emits ``\/`` on its own, so nothing is double
    # escaped — and yes, this escapes the slashes inside the URL too. That is
    # the behaviour the panel was proven against.
    return json.dumps(document).replace("/", "\\/").encode("utf-8")


def push(host: str, pin: str, url: str, mac: str | None = None) -> None:
    """Tell the display to fetch ``url`` (MDC ``set_content_download``, TLS 1515)."""
    command = ["node", str(PUSH_SCRIPT), host, pin, url]
    if mac:
        command.append(mac)
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=PUSH_TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"display did not answer within {PUSH_TIMEOUT_S}s") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise RuntimeError(
            f"MDC push failed ({completed.returncode}): "
            + (" | ".join(detail[-3:]) if detail else "no output")
        )
    _LOGGER.info("Pushed %s to %s", url, host)


def probe(host: str, pin: str, mac: str | None = None) -> dict[str, object]:
    """Ask the display who it is (MDC read over TLS 1515).

    What ``binary_sensor.epaperengine_display_reachable`` is built on
    [Festlegung 2026-08-21]: reachable means *the PIN was accepted and the panel
    answered*, not merely that port 1515 is open. Raises ``RuntimeError`` when
    the connection or the handshake fails — that is the "not reachable" case.
    """
    command = ["node", str(PROBE_SCRIPT), host, pin]
    if mac:
        command.append(mac)
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=PROBE_TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"display did not answer within {PROBE_TIMEOUT_S}s") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise RuntimeError(
            f"MDC probe failed ({completed.returncode}): "
            + (" | ".join(detail[-3:]) if detail else "no output")
        )
    try:
        return dict(json.loads(completed.stdout or "{}"))
    except ValueError as exc:
        raise RuntimeError(f"MDC probe returned no JSON: {completed.stdout[:200]}") from exc


def copy_to_media(pairs: list[tuple[bytes, Path]]) -> str | None:
    """Write the frontend copies — **best effort** (FSD §3.4).

    The media tree lives on the NAS. A NAS that is rebooting must not turn a
    successful render into a failed run, so every failure here becomes a warning
    on the status sensor and nothing more. The display is served from ``/data``
    and never touches this.
    """
    failures: list[str] = []
    for payload, target in pairs:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        except OSError as exc:
            failures.append(f"{target}: {exc}")
    if failures:
        message = "media copy failed: " + " | ".join(failures)
        _LOGGER.warning(message)
        return message
    return None
