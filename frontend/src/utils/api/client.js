import { apiUrl } from '../constants/api';
import {
  WAKEUP_DELAY_MS,
  RETRY_AFTER_502_MS,
  FETCH_TIMEOUT_MS,
} from '../constants/timing';

function defaultFetchTimeoutSignal() {
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
    return AbortSignal.timeout(FETCH_TIMEOUT_MS);
  }
  const c = new AbortController();
  setTimeout(() => c.abort(), FETCH_TIMEOUT_MS);
  return c.signal;
}

/**
 * fetch wrapper that:
 *  1. Fires `onWakingUp` callback if the request takes longer than WAKEUP_DELAY_MS
 *     (indicating the Render free-tier server is spinning up).
 *  2. Automatically retries once on a 502 Bad Gateway after RETRY_AFTER_502_MS.
 *  3. Aborts after FETCH_TIMEOUT_MS when no custom `signal` is passed (hung DB / network).
 */
export async function fetchWithWakeup(url, options = {}, { onWakingUp } = {}) {
  const wakeupTimer = setTimeout(() => {
    onWakingUp?.();
  }, WAKEUP_DELAY_MS);
  const signal = options.signal ?? defaultFetchTimeoutSignal();

  try {
    let res = await fetch(apiUrl(url), { ...options, signal });
    clearTimeout(wakeupTimer);

    if (res.status === 502 && onWakingUp) {
      onWakingUp();
      await new Promise((r) => setTimeout(r, RETRY_AFTER_502_MS));
      res = await fetch(apiUrl(url), {
        ...options,
        signal: options.signal ?? defaultFetchTimeoutSignal(),
      });
    }
    return res;
  } catch (err) {
    clearTimeout(wakeupTimer);
    throw err;
  }
}
