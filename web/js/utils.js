/*
Module: utils.js

Variables exported:
- `wait(ms)`: Promise-based timeout helper for short UI animation delays.
- `toInt(...)`: guarded integer parser with min/max clamping.

How this module works:
- Provides small reusable utility helpers for other UI modules.
*/

export function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function toInt(value, fallback, minValue, maxValue = null) {
  const parsed = Number.parseInt(String(value), 10);
  let result = Number.isNaN(parsed) ? fallback : parsed;

  if (result < minValue) {
    result = minValue;
  }
  if (maxValue !== null && result > maxValue) {
    result = maxValue;
  }
  return result;
}
