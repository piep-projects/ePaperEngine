#!/usr/bin/env node
/**
 * One MDC transaction: connect over TLS:1515 with the PIN, hand the display the
 * URL of our manifest, disconnect.
 *
 * This is the *only* reason Node is in the image. Rendering needs none of it —
 * `chromium-headless-shell` is driven straight from Python (renderer.py).
 *
 * `@weejewel/samsung-mdc` is the protocol layer underneath the command-line tool
 * that proved the path on 2026-08-19. The tool itself is not used, because it
 * serves the image from a throwaway server that dies as soon as the display has
 * fetched it once; see the docstring of delivery.py.
 *
 * Usage: node push.mjs <host> <pin> <content-json-url> [mac]
 */

import { Device } from '@weejewel/samsung-mdc';

const [host, pin, url, mac] = process.argv.slice(2);

if (!host || !pin || !url) {
  console.error('usage: push.mjs <host> <pin> <content-json-url> [mac]');
  process.exit(2);
}

const device = new Device({ host, pin, ...(mac ? { mac } : {}) });

try {
  if (mac) {
    // Wake-on-LAN before talking. Harmless while the panel is on mains power,
    // and it is the flow that was proven; phase 7 leans on it properly.
    await device.wakeup();
    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  await device.connect();
  await device.setContentDownload({ url });
  await device.disconnect();
  console.log(`set_content_download -> ${url}`);
} catch (err) {
  // Plain text on stderr: it travels through delivery.py into
  // sensor.epaperengine_status, where somebody has to read it without a log.
  console.error(err?.message ?? String(err));
  process.exit(1);
}
