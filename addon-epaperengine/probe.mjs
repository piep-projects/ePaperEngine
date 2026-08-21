#!/usr/bin/env node
/**
 * One MDC read transaction: connect over TLS:1515 with the PIN, ask the display
 * who it is, disconnect. Prints a JSON object on stdout.
 *
 * This is what `binary_sensor.epaperengine_display_reachable` is measured with
 * [Festlegung 2026-08-21]: a TCP connect to :1515 would only prove that a port
 * is open — it would call a display with a wrong PIN "reachable", which is the
 * one failure the sensor exists to catch. Here the PIN has to be accepted and
 * the panel has to answer a real command before anything reports success.
 *
 * Every field is queried on its own and a failing one is recorded rather than
 * fatal: an EM32DX that answers `getDeviceName` but not `getBatteryState` is
 * still reachable, and the panel page would rather show one blank row than no
 * page. Only `connect()` failing means unreachable.
 *
 * Usage: node probe.mjs <host> <pin> [mac]
 */

import { Device } from '@weejewel/samsung-mdc';

const [host, pin, mac] = process.argv.slice(2);

if (!host || !pin) {
  console.error('usage: probe.mjs <host> <pin> [mac]');
  process.exit(2);
}

const device = new Device({ host, pin, ...(mac ? { mac } : {}) });

/** Run one getter; a refusal becomes a recorded reason, not an abort. */
async function ask(fields, key, fn) {
  try {
    fields[key] = await fn();
  } catch (err) {
    fields[key] = null;
    fields.unavailable = [...(fields.unavailable ?? []), `${key}: ${err?.message ?? err}`];
  }
}

const fields = {};

try {
  // No wakeup() here, unlike push.mjs: a probe must report what *is*, and waking
  // the panel to answer the question "are you awake" would make the sensor lie.
  await device.connect();
} catch (err) {
  console.error(err?.message ?? String(err));
  process.exit(1);
}

try {
  await ask(fields, 'device_name', () => device.getDeviceName());
  await ask(fields, 'software_version', () => device.getSoftwareVersion());
  await ask(fields, 'serial_number', () => device.getSerialNumber());
  await ask(fields, 'power_state', () => device.getPowerState());
  // Phase 7 (battery operation) reads this; it costs one command to have it now.
  await ask(fields, 'battery', () => device.getBatteryState());
} finally {
  try {
    await device.disconnect();
  } catch {
    // Already gone — the answers above are what the caller came for.
  }
}

console.log(JSON.stringify(fields));
