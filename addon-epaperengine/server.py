#!/usr/bin/env python3
"""ePaperEngine add-on — control and delivery on one port (FSD §3.2).

One process, one port, one log: the display fetches ``/content.json`` and
``/image`` from here, and Home Assistant triggers a run through ``/render``.

State of this version (phase 3, steps 1–3): the server, the queue and the
conversation with Home Assistant are in place. The renderer itself — Jinja,
Chromium, dithering, MDC push — is still missing; a run therefore reports
``render_failed`` with a plain-text reason rather than pretending to work.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

_LOGGER = logging.getLogger("epaperengine")

PORT = 8099
DATA_DIR = Path("/data")
IMAGE_PATH = DATA_DIR / "current.png"
CONTENT_PATH = DATA_DIR / "content.json"

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

# ``host_network: true`` does **not** cut the add-on off from the supervisor:
# Supervisor writes ``172.30.32.2 supervisor`` into the container's /etc/hosts,
# and that entry survives the host namespace [measured 2026-08-21 on the test
# instance]. The literal address is kept only as a fallback — and it is .2, the
# supervisor itself; .1 is the bridge gateway and refuses the connection.
API_BASES = ("http://supervisor/core/api", "http://172.30.32.2/core/api")


class Engine:
    """Owns the run queue and the conversation with Home Assistant."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        self._api_base: str | None = None
        self.last_run: dict[str, Any] | None = None
        self.runs = 0

    # --- Home Assistant -------------------------------------------------------
    async def _call(
        self, session: aiohttp.ClientSession, path: str, payload: dict[str, Any]
    ) -> Any:
        """POST to the HA core API through the supervisor proxy."""
        bases = [self._api_base] if self._api_base else list(API_BASES)
        # Collect *every* failure, not just the last one. Keeping only the last
        # made a real outage unreadable: the message named the fallback address
        # while the actual problem was on the first base, and the first error was
        # logged at DEBUG where nobody sees it.
        failures: list[str] = []
        for base in bases:
            try:
                async with session.post(
                    f"{base}{path}",
                    json=payload,
                    headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    body = await resp.text()
                    if resp.status >= 400:
                        raise RuntimeError(f"HTTP {resp.status}: {body[:300]}")
                    if self._api_base != base:
                        self._api_base = base
                        _LOGGER.info("Home Assistant API reachable at %s", base)
                    return json.loads(body) if body else None
            except Exception as exc:  # noqa: BLE001 - try the next base
                detail = f"{base} -> {type(exc).__name__}: {exc}"
                failures.append(detail)
                _LOGGER.warning("API base unusable: %s", detail)
        # A base that worked before and fails now must not stay pinned.
        self._api_base = None
        raise RuntimeError("no HA API base reachable; " + " | ".join(failures))

    async def get_render_data(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """Pull the render document (FSD §6.2 step 1).

        ``?return_response`` belongs in the **query**, not the body — the body
        carries service data only, and a flag in there earns a 400.
        """
        res = await self._call(
            session, "/services/epaperengine/get_render_data?return_response", {}
        )
        return dict((res or {}).get("service_response") or {})

    async def report_run(
        self, session: aiohttp.ClientSession, **fields: Any
    ) -> None:
        """Report the outcome (FSD §6.2 step 10)."""
        await self._call(
            session,
            "/services/epaperengine/report_run",
            {k: v for k, v in fields.items() if v is not None},
        )

    # --- queue ----------------------------------------------------------------
    def enqueue(self, reason: str) -> None:
        """Queue a run, *last wins* (FSD §6.1).

        A depth of one is the whole mechanism: if a run is already waiting, the
        pending one is replaced rather than added to. Two runs racing for the
        same file is exactly what this prevents.
        """
        while True:
            try:
                self._queue.put_nowait(reason)
                return
            except asyncio.QueueFull:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    pass

    async def worker(self) -> None:
        async with aiohttp.ClientSession() as session:
            while True:
                reason = await self._queue.get()
                try:
                    await self._run_once(session, reason)
                except Exception as exc:  # noqa: BLE001 - a run must never kill the worker
                    _LOGGER.exception("Run failed: %s", exc)
                    self.last_run = {"reason": reason, "error": str(exc)}
                finally:
                    self._queue.task_done()

    async def _run_once(self, session: aiohttp.ClientSession, reason: str) -> None:
        self.runs += 1
        document = await self.get_render_data(session)
        view = str(document.get("view") or "error")
        _LOGGER.info(
            "Run %d (%s): view=%s photo slot=%s",
            self.runs, reason, view, (document.get("photos") or {}).get("slot"),
        )
        self.last_run = {"reason": reason, "view": view, "document": document}

        # Honest placeholder: the renderer does not exist yet. Reporting success
        # here would put a lie into the status sensor.
        await self.report_run(
            session,
            result="render_failed",
            view=view,
            error="renderer not implemented yet (phase 3, steps 5-9)",
        )


engine = Engine()


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "runs": engine.runs,
            "queued": engine._queue.qsize(),
            "api_base": engine._api_base,
            "renderer": "not implemented",
            "last_run": engine.last_run,
        }
    )


async def handle_render(request: web.Request) -> web.Response:
    """Answer 202 immediately, work asynchronously (FSD §3.2)."""
    reason = request.query.get("reason", "http")
    engine.enqueue(reason)
    return web.json_response({"queued": True}, status=202)


async def handle_content(_request: web.Request) -> web.Response:
    if not CONTENT_PATH.exists():
        return web.json_response({"error": "no content yet"}, status=404)
    return web.Response(body=CONTENT_PATH.read_bytes(), content_type="application/json")


async def handle_image(_request: web.Request) -> web.Response:
    if not IMAGE_PATH.exists():
        return web.json_response({"error": "no image yet"}, status=404)
    return web.Response(body=IMAGE_PATH.read_bytes(), content_type="image/png")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post("/render", handle_render)
    app.router.add_get("/content.json", handle_content)
    app.router.add_get("/image", handle_image)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    _LOGGER.info("ePaperEngine add-on listening on :%d", PORT)

    await engine.worker()


if __name__ == "__main__":
    asyncio.run(main())
