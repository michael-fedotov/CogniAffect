import { apiUrl } from '../constants/api';
import { WAKEUP_DELAY_MS, RETRY_AFTER_502_MS } from '../constants/timing';

/**
 * fetch wrapper that:
 *  1. Fires `onWakingUp` callback if the request takes longer than WAKEUP_DELAY_MS
 *     (indicating the Render free-tier server is spinning up).
 *  2. Automatically retries once on a 502 Bad Gateway after RETRY_AFTER_502_MS.
 */
export async function fetchWithWakeup(url, options = {}, { onWakingUp } = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    onWakingUp?.();
  }, WAKEUP_DELAY_MS);

  try {
    let res = await fetch(apiUrl(url), { ...options, signal: controller.signal });
    clearTimeout(timeoutId);

    if (res.status === 502 && onWakingUp) {
      onWakingUp();
      await new Promise((r) => setTimeout(r, RETRY_AFTER_502_MS));
      res = await fetch(apiUrl(url), options);
    }
    return res;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}
