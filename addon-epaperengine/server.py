#!/usr/bin/env python3
"""ePaperEngine add-on — control and delivery on one port (FSD §3.2).

One process, one port, one log: the display fetches ``/content.json`` and
``/image`` from here, and Home Assistant triggers a run through ``/render``.

The full vertical slice of FSD §6.2 runs here: pull the state from Home
Assistant, keep the photo cache, fill a Jinja template, shoot it with Chromium
at 2560×1440, dither it onto the six Spectra primaries, compare the hash, serve
it, push it over MDC, copy it to the media tree, report the outcome. The work
itself lives in the modules next to this one; what is here is the server, the
queue and the order of the steps.

Since phase 5 the run is split in two halves that fail differently: rendering a
view (``_render_view``, one branch per view) and delivering the result
(``_deliver``, the same for all of them). Between the two sits the policy of
FSD §12 — count the failures, and from the second in a row put the failure
itself on the wall.

The pipeline is blocking — Pillow, Chromium and Node all are — so it runs in a
worker thread and the event loop stays free to answer ``/image`` while the
display is fetching it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web
from PIL import Image

import delivery
import imaging
import outage
import paths as media_layout
import recipe_layout
import renderer
import wall_text
from photocache import PhotoCache

_LOGGER = logging.getLogger("epaperengine")

PORT = 8099
DATA_DIR = Path("/data")
IMAGE_PATH = DATA_DIR / "current.png"
CONTENT_PATH = DATA_DIR / "content.json"
PREVIEW_PATH = DATA_DIR / "preview.jpg"
STATE_PATH = DATA_DIR / "state.json"
HASH_MEMO_PATH = DATA_DIR / "photo_hashes.json"
WORK_DIR = DATA_DIR / "render"

# Result tokens of ``sensor.epaperengine_status``. Kept in step with the
# integration's ``const.py``; the sensor is an ENUM and rejects anything else.
RESULT_PUSHED = "pushed"
RESULT_UNCHANGED = "unchanged"
RESULT_PUSH_FAILED = "push_failed"
RESULT_RENDER_FAILED = "render_failed"

# Empty unless the entrypoint ran through ``with-contenv`` (see run.sh) — s6
# does not pass the container environment to its services on its own.
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

# ``host_network: true`` does **not** cut the add-on off from the supervisor:
# Supervisor writes ``172.30.32.2 supervisor`` into the container's /etc/hosts,
# and that entry survives the host namespace [measured 2026-08-21 on the test
# instance]. The literal address is kept only as a fallback — and it is .2, the
# supervisor itself; .1 is the bridge gateway and refuses the connection.
API_BASES = ("http://supervisor/core/api", "http://172.30.32.2/core/api")


@dataclass
class Outcome:
    """What one run produced. Travels straight into ``report_run``."""

    result: str
    view: str
    image_hash: str | None = None
    pushed: bool = False
    error: str | None = None
    warning: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def as_report(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "view": self.view,
            "image_hash": self.image_hash,
            "pushed": self.pushed,
            "error": self.error,
            "warning": self.warning,
        }


@dataclass
class Job:
    """One queued run.

    ``force`` is the panel's "Push now" (FSD §3.1): send the current image even
    when it is unchanged, i.e. step over the hash gate of §11. It rides on the
    job rather than on the engine because two jobs can be in flight around one
    another and a forced push must not leak into the next timed run.
    """

    reason: str
    force: bool = False


class Engine:
    """Owns the run queue and the conversation with Home Assistant."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=1)
        self._api_base: str | None = None
        self.last_run: dict[str, Any] | None = None
        self.last_cache: dict[str, Any] | None = None
        self.runs = 0
        # Proof that the display actually came and took it. The MDC call only
        # says the panel accepted the order, not that it fetched anything.
        self.last_fetch: dict[str, Any] | None = None
        # Last answer of the MDC probe, with the moment it was taken. Both the
        # reachability sensor and the panel's "Test connection" read this.
        self.display: dict[str, Any] | None = None
        self._probe_lock = asyncio.Lock()

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
    def enqueue(self, reason: str, force: bool = False) -> None:
        """Queue a run, *last wins* (FSD §6.1).

        A depth of one is the whole mechanism: if a run is already waiting, the
        pending one is replaced rather than added to. Two runs racing for the
        same file is exactly what this prevents.

        ``force`` survives the replacement even when the newer job does not carry
        it: somebody pressed "Push now", and a timed run arriving a second later
        must not quietly swallow that request.
        """
        while True:
            try:
                self._queue.put_nowait(Job(reason, force))
                return
            except asyncio.QueueFull:
                try:
                    dropped = self._queue.get_nowait()
                    self._queue.task_done()
                    force = force or dropped.force
                except asyncio.QueueEmpty:
                    pass

    async def probe_display(
        self, session: aiohttp.ClientSession, max_age_s: float = 30.0
    ) -> dict[str, Any]:
        """Ask the display who it is, at most once every ``max_age_s``.

        Two callers share this: the reachability sensor on its timer and the
        panel's "Test connection" button. The cache is what keeps an impatient
        finger on that button from queuing a dozen TLS handshakes; passing
        ``max_age_s=0`` forces a fresh one.
        """
        now = time.time()
        cached = self.display
        if cached and max_age_s > 0 and now - float(cached.get("at_ts") or 0) < max_age_s:
            return cached

        async with self._probe_lock:
            # Somebody may have refreshed it while we waited for the lock.
            cached = self.display
            if cached and max_age_s > 0 and time.time() - float(cached.get("at_ts") or 0) < max_age_s:
                return cached

            display_cfg = (await self.get_render_data(session)).get("display") or {}
            host, pin = display_cfg.get("host"), display_cfg.get("mdc_pin")
            if not host or not pin:
                result: dict[str, Any] = {
                    "reachable": False,
                    "error": "display.host or display.mdc_pin is not configured",
                }
            else:
                try:
                    fields = await asyncio.to_thread(
                        delivery.probe,
                        str(host),
                        str(pin),
                        str(display_cfg["mac"]) if display_cfg.get("mac") else None,
                    )
                    result = {"reachable": True, "host": host, **fields}
                except RuntimeError as exc:
                    result = {"reachable": False, "host": host, "error": str(exc)}
            result["at_ts"] = time.time()
            result["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.display = result
            return result

    async def worker(self) -> None:
        async with aiohttp.ClientSession() as session:
            while True:
                job = await self._queue.get()
                try:
                    await self._run_once(session, job)
                except Exception as exc:  # noqa: BLE001 - a run must never kill the worker
                    _LOGGER.exception("Run failed: %s", exc)
                    self.last_run = {"reason": job.reason, "error": str(exc)}
                finally:
                    self._queue.task_done()

    async def _run_once(self, session: aiohttp.ClientSession, job: Job) -> None:
        self.runs += 1
        started = time.monotonic()
        document = await self.get_render_data(session)
        view = str(document.get("view") or "error")

        try:
            # Blocking from here to the end of the pipeline: Pillow, Chromium and
            # Node. In a thread, so ``/image`` stays answerable — the display
            # fetches it while this very run is still finishing.
            outcome = await asyncio.to_thread(run_pipeline, document, view, self, job.force)
        except Exception as exc:  # noqa: BLE001 - a bad run is a reported run
            _LOGGER.exception("Pipeline failed")
            outcome = Outcome(
                result=RESULT_RENDER_FAILED, view=view, error=f"{type(exc).__name__}: {exc}"
            )

        seconds = time.monotonic() - started
        self.last_run = {
            "reason": job.reason,
            "forced": job.force,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seconds": round(seconds, 2),
            **outcome.as_report(),
            **outcome.detail,
        }
        _LOGGER.info(
            "Run %d (%s): %s in %.1fs%s",
            self.runs,
            job.reason + (" force" if job.force else ""),
            outcome.result,
            seconds,
            f" — {outcome.error}" if outcome.error else "",
        )
        await self.report_run(session, **outcome.as_report())


def _read_state() -> dict[str, Any]:
    try:
        return dict(json.loads(STATE_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _write_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")


# --- the views ----------------------------------------------------------------
# Stable English tokens, the same ones ``const.py`` defines on the integration
# side (FSD §3.0a). The add-on only ever sees them, never a label.
VIEW_PHOTOS = "photos"
VIEW_RECIPES = "recipes"
VIEW_ERROR = "error"

# The failure policy itself lives in ``outage.py``: counting and timing are the
# part worth testing without waiting for it [Festlegung P10, 2026-08-21].


class ViewNotBuilt(RuntimeError):
    """The resolved view has no template yet.

    A failure like any other: it counts towards the streak in ``outage.py`` and,
    if it persists, ends up legibly on the wall instead of leaving a stale
    picture hanging with nobody told why.
    """


def _render_view(
    document: dict[str, Any],
    view: str,
    engine: Engine,
    state: dict[str, Any],
    text: wall_text.WallText,
) -> tuple[Image.Image, dict[str, Any]]:
    """Turn the render document into the finished, dithered image.

    Everything that can legitimately fail lives in here — reading the NAS,
    Chromium, a view nobody has built yet — so that ``run_pipeline`` has exactly
    one place to catch and one policy to apply.
    """
    if view == VIEW_PHOTOS:
        return _render_photos(document, engine)
    if view == VIEW_RECIPES:
        return _render_recipes(document, text)
    if view == VIEW_ERROR:
        # Somebody pinned the error view by hand (FSD §5 allows it — ``error`` is
        # one of the five tokens). Show the outage on record; if there is none,
        # say so rather than inventing one.
        standing = outage.standing(state)
        return (
            _render_error(
                standing.technical if standing else text("error.idle"),
                standing.since if standing else None,
                text,
            ),
            {"error_page": "on request"},
        )
    raise ViewNotBuilt(f"view '{view}' has no template yet (phase 5)")


def _render_photos(
    document: dict[str, Any], engine: Engine
) -> tuple[Image.Image, dict[str, Any]]:
    """The photo view (FSD §8.3) — steps 3 to 5 of §6.2."""
    photos_cfg = document.get("photos") or {}
    layout = media_layout.media_paths((document.get("media") or {}).get("root"))
    layout.ensure()

    source = media_layout.source_folder(layout, photos_cfg.get("source_folder"))
    cache = PhotoCache(
        source=source,
        processed=layout.processed_photos,
        preview=layout.preview_photos,
        memo_path=HASH_MEMO_PATH,
    )
    report = cache.refresh()
    engine.last_cache = {
        "folder": str(source),
        "total": report.total,
        "added": report.added,
        "removed": report.removed,
        "unreadable": report.unreadable,
    }
    photo = cache.pick(int(photos_cfg.get("slot") or 0))

    html = renderer.render_html(
        VIEW_PHOTOS,
        {"photo_url": photo.crop.as_uri(), "photo_name": photo.source},
        WORK_DIR,
    )
    shot = renderer.screenshot(html, WORK_DIR / "shot.png", WORK_DIR)
    return imaging.dither_spectra(shot), {
        "photo": photo.source,
        "photos_total": report.total,
    }


def _render_recipes(
    document: dict[str, Any], text: wall_text.WallText
) -> tuple[Image.Image, dict[str, Any]]:
    """The recipe view (FSD §8.2, §9).

    **No network call happens here.** The full text of the selected recipes
    travels in the render document (FSD §9.1) because the API is documented to
    ban by IP and a fetch per render run is exactly what FSD §9.2 forbids. If a
    recipe is missing from the document, it is missing from the cache — the
    integration is where that gets fixed, not here.
    """
    recipes = (document.get("recipes") or {}).get("items") or []
    columns = recipe_layout.build_columns(recipes)

    html = renderer.render_html(
        VIEW_RECIPES,
        {
            "language": text.language,
            "t": text,
            "columns": [column.as_dict() for column in columns],
        },
        WORK_DIR,
    )
    shot = renderer.screenshot(html, WORK_DIR / "recipes.png", WORK_DIR)
    return imaging.dither_spectra(shot), {
        "recipes": [column.name for column in columns],
        "font_px": [column.font_px for column in columns],
        "truncated": sum(1 for column in columns if column.truncated),
    }


def _render_error(
    technical: str, since: datetime | None, text: wall_text.WallText
) -> Image.Image:
    """The error page (FSD §8.5): sentence, time, one technical line [P11].

    ``since`` is the **start of the failure streak**, not the moment of this
    run, and that is load-bearing rather than cosmetic: a page carrying the
    current time would differ on every run and push every 15 minutes. Held
    still, the page is pixel-identical, the hash gate of FSD §11 catches it, and
    a permanent outage costs exactly one refresh — the "günstige Nebenwirkung"
    §12 promises.
    """
    html = renderer.render_html(
        VIEW_ERROR,
        {
            "language": text.language,
            "t": text,
            "technical": technical,
            "since": text.moment(since) if since else "",
        },
        WORK_DIR,
    )
    shot = renderer.screenshot(html, WORK_DIR / "error.png", WORK_DIR)
    return imaging.dither_spectra(shot)


def run_pipeline(
    document: dict[str, Any], view: str, engine: Engine, force: bool = False
) -> Outcome:
    """FSD §6.2, steps 2 to 9. Blocking; called through ``asyncio.to_thread``.

    ``force`` steps over the hash gate of §11 and nothing else — the picture is
    still rendered from scratch, so what goes to the wall is the current state
    and not a stale file replayed from ``/data``.
    """
    state = _read_state()
    # The wall follows hass.language (FSD §3.0a, Festlegung P9) — the token
    # travels in the render document, the catalogs live in templates/i18n/.
    text = wall_text.WallText(document.get("language"))

    try:
        final, detail = _render_view(document, view, engine, state, text)
    except Exception as exc:  # noqa: BLE001 - every failure takes the same road
        return _run_error_page(document, view, exc, state, text, force)

    # A run that got through ends the streak. Not cleared while the *error* view
    # is what was asked for: the page would otherwise wipe the very text it is
    # showing and differ from itself on the next run.
    if view != VIEW_ERROR and outage.clear(state):
        _LOGGER.info("Failure streak ended by a successful %s run", view)

    return _deliver(final, view, document, state, force, detail)


def _run_error_page(
    document: dict[str, Any],
    view: str,
    exc: BaseException,
    state: dict[str, Any],
    text: wall_text.WallText,
    force: bool,
) -> Outcome:
    """What a failed run does (FSD §12, Festlegung P10).

    Counts the streak, and from the second failure on renders the failure itself
    and sends it to the wall. The status sensor says ``render_failed`` either
    way — the run *did* fail — while ``view: error`` together with ``pushed``
    is what tells card and panel that the wall is now showing the fault.
    """
    hit = outage.note_failure(state, view, exc, datetime.now())
    technical, failures = hit.technical, hit.failures
    _LOGGER.warning("Run failed (%d in a row): %s", failures, technical)

    if not hit.show_on_wall:
        # The grace run: the picture stays, Home Assistant already knows.
        _write_state(state)
        return Outcome(
            result=RESULT_RENDER_FAILED,
            view=view,
            error=technical,
            detail={"failures": failures, "error_page": "held back"},
        )

    try:
        final = _render_error(technical, hit.since, text)
    except Exception as inner:  # noqa: BLE001 - nothing left to fall back on
        _LOGGER.exception("The error page failed to render")
        _write_state(state)
        return Outcome(
            result=RESULT_RENDER_FAILED,
            view=view,
            error=f"{technical} | error page failed too: {type(inner).__name__}: {inner}",
            detail={"failures": failures, "error_page": "failed"},
        )

    outcome = _deliver(
        final, VIEW_ERROR, document, state, force, {"failed_view": view}
    )
    return Outcome(
        result=RESULT_RENDER_FAILED,
        view=VIEW_ERROR,
        image_hash=outcome.image_hash,
        pushed=outcome.pushed,
        error=technical if not outcome.error else f"{technical} | error page: {outcome.error}",
        warning=outcome.warning,
        detail={**outcome.detail, "failures": failures, "error_page": outcome.result},
    )


def _deliver(
    final: Image.Image,
    view: str,
    document: dict[str, Any],
    state: dict[str, Any],
    force: bool,
    detail: dict[str, Any],
) -> Outcome:
    """Steps 6 to 10 of §6.2 — the half that is the same for every view."""
    display_cfg = document.get("display") or {}
    layout = media_layout.media_paths((document.get("media") or {}).get("root"))

    # --- step 6: has anything changed? ---------------------------------------
    digest = delivery.fingerprint(final)
    if force:
        detail = {**detail, "forced": True}
    if not force and state.get("image_hash") == digest and IMAGE_PATH.exists():
        # The normal outcome, not an error (FSD §11). A standing error page
        # suppresses its own repeat pushes through exactly this branch.
        _write_state(state)
        return Outcome(
            result=RESULT_UNCHANGED, view=view, image_hash=digest, detail=detail
        )

    # --- steps 7 and 8: serve from /data -------------------------------------
    # Local, never from the media tree: a NAS reboot must not make the display
    # reach into thin air while fetching (FSD §3.4).
    imaging.save_png(final, IMAGE_PATH)
    preview = imaging.preview_bytes(final, imaging.PREVIEW_CURRENT)
    PREVIEW_PATH.write_bytes(preview)

    host = display_cfg.get("host")
    pin = display_cfg.get("mdc_pin")
    if not host or not pin:
        _write_state({**state, "image_hash": digest})
        return Outcome(
            result=RESULT_PUSH_FAILED,
            view=view,
            image_hash=digest,
            error="display.host or display.mdc_pin is not configured",
            detail=detail,
        )

    local_ip = delivery.local_ip_towards(str(host))
    CONTENT_PATH.write_bytes(
        delivery.build_content_json(
            image_url=f"http://{local_ip}:{PORT}/image",
            image_size=IMAGE_PATH.stat().st_size,
        )
    )

    # --- step 9 of the plan: MDC ---------------------------------------------
    try:
        delivery.push(
            host=str(host),
            pin=str(pin),
            url=f"http://{local_ip}:{PORT}/content.json",
            mac=str(display_cfg["mac"]) if display_cfg.get("mac") else None,
        )
    except RuntimeError as exc:
        # The image is rendered and served; only the display stayed mute. The
        # hash is stored anyway — the next run would otherwise re-push an
        # identical picture forever (FSD §12: try again on the next run).
        _write_state({**state, "image_hash": digest})
        return Outcome(
            result=RESULT_PUSH_FAILED,
            view=view,
            image_hash=digest,
            error=str(exc),
            detail={**detail, "local_ip": local_ip},
        )

    _write_state({**state, "image_hash": digest, "pushed_at": time.time()})

    # --- step 10: the copies for the frontend, best effort -------------------
    warning = delivery.copy_to_media(
        [
            (IMAGE_PATH.read_bytes(), layout.wall / "current.png"),
            (preview, layout.preview / "current.jpg"),
        ]
    )
    return Outcome(
        result=RESULT_PUSHED,
        view=view,
        image_hash=digest,
        pushed=True,
        warning=warning,
        detail={**detail, "local_ip": local_ip},
    )

engine = Engine()


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "runs": engine.runs,
            "queued": engine._queue.qsize(),
            "api_base": engine._api_base,
            "chromium": Path(renderer.CHROMIUM).exists(),
            "has_image": IMAGE_PATH.exists(),
            "photo_cache": engine.last_cache,
            "last_run": engine.last_run,
            "last_fetch": engine.last_fetch,
            "display": engine.display,
        }
    )


def _flag(request: web.Request, name: str) -> bool:
    """A query flag, present-means-true: ``?force``, ``?force=1``, ``?force=true``."""
    if name not in request.query:
        return False
    return request.query[name].lower() not in ("0", "false", "no")


async def handle_render(request: web.Request) -> web.Response:
    """Answer 202 immediately, work asynchronously (FSD §3.2).

    ``?force`` is the panel's "Push now": render as always, but push even when
    the image is unchanged.
    """
    reason = request.query.get("reason", "http")
    force = _flag(request, "force")
    engine.enqueue(reason, force)
    return web.json_response({"queued": True, "force": force}, status=202)


async def handle_display(request: web.Request) -> web.Response:
    """MDC reachability of the display — the honest kind (FSD §3.1).

    Answers 200 with ``reachable: false`` and a reason rather than an HTTP error:
    "the display is mute" is an answer to the question, not a failure to answer
    it, and the sensor behind this needs to tell the two apart.
    """
    fresh = _flag(request, "fresh")
    async with aiohttp.ClientSession() as session:
        result = await engine.probe_display(session, max_age_s=0 if fresh else 30.0)
    return web.json_response(result)


def _note_fetch(request: web.Request, what: str) -> None:
    """Record who came for the file — the only proof the display took it.

    The MDC call only says the panel *accepted* the order. A line here with the
    display's own address is what turns that into evidence, so the address is
    named rather than assumed: during development the same endpoints get pulled
    from a laptop, and a log that calls every caller "the display" would have
    made the first real fetch indistinguishable from a curl.
    """
    engine.last_fetch = {
        "what": what,
        "from": request.remote,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _LOGGER.info("%s fetched by %s", what, request.remote)


async def handle_content(request: web.Request) -> web.Response:
    if not CONTENT_PATH.exists():
        return web.json_response({"error": "no content yet"}, status=404)
    _note_fetch(request, "content.json")
    # Served as raw bytes: the document carries escaped slashes that must reach
    # the panel exactly as written (FSD §10.1).
    return web.Response(body=CONTENT_PATH.read_bytes(), content_type="application/json")


async def handle_image(request: web.Request) -> web.Response:
    if not IMAGE_PATH.exists():
        return web.json_response({"error": "no image yet"}, status=404)
    _note_fetch(request, "image")
    return web.Response(body=IMAGE_PATH.read_bytes(), content_type="image/png")


async def handle_preview(_request: web.Request) -> web.Response:
    """Small JPEG of the current wall image — for eyeballing during development."""
    if not PREVIEW_PATH.exists():
        return web.json_response({"error": "no preview yet"}, status=404)
    return web.Response(body=PREVIEW_PATH.read_bytes(), content_type="image/jpeg")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if not SUPERVISOR_TOKEN:
        _LOGGER.error(
            "SUPERVISOR_TOKEN is empty — every call to Home Assistant will answer "
            "401. Is the entrypoint running through with-contenv (run.sh)?"
        )

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post("/render", handle_render)
    app.router.add_get("/display", handle_display)
    app.router.add_get("/content.json", handle_content)
    app.router.add_get("/image", handle_image)
    app.router.add_get("/preview", handle_preview)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    _LOGGER.info("ePaperEngine add-on listening on :%d", PORT)

    await engine.worker()


if __name__ == "__main__":
    asyncio.run(main())
