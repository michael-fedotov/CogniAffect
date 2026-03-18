import { useState, useEffect, useRef, useCallback } from 'react';
import { saveToLocalStorage } from '../utils/storage/localSessionStorage';
import { syncToServer } from '../utils/api/annotationApi';
import { ACTION_TYPES } from '../state/annotationActionTypes';
import {
  AUTOSAVE_INTERVAL_MS,
  SYNC_DEBOUNCE_MS,
} from '../utils/constants/timing';

/**
 * Wires up auto-save (localStorage + server sync) for an annotation session.
 *
 * Returns:
 *  - `lastSavedAt`   — timestamp of the most recent local save
 *  - `serverStatus`  — 'idle' | 'syncing' | 'synced' | 'waking' | 'offline'
 *  - `saveNow`       — call to trigger an immediate manual save + sync
 */
export function useAutoSync(state, dispatch) {
  const [lastSavedAt, setLastSavedAt] = useState(state.lastSavedAt);
  const [serverStatus, setServerStatus] = useState('idle');

  // Keep a stable ref to current state so interval/timeout callbacks
  // always read fresh state without being recreated on every render.
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const doServerSync = useCallback(async () => {
    setServerStatus('syncing');
    const ok = await syncToServer(stateRef.current, {
      onWakingUp: () => setServerStatus('waking'),
    });
    setServerStatus(ok ? 'synced' : 'offline');
  }, []);

  const saveNow = useCallback(() => {
    saveToLocalStorage(stateRef.current);
    const now = Date.now();
    dispatch({ type: ACTION_TYPES.MARK_SAVED, timestamp: now });
    setLastSavedAt(now);
    doServerSync();
  }, [dispatch, doServerSync]);

  // Auto-save on a 30-second interval (stable — uses stateRef)
  useEffect(() => {
    const interval = setInterval(() => {
      saveToLocalStorage(stateRef.current);
      const now = Date.now();
      dispatch({ type: ACTION_TYPES.MARK_SAVED, timestamp: now });
      setLastSavedAt(now);
      doServerSync();
    }, AUTOSAVE_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [dispatch, doServerSync]);

  // Debounced server sync whenever annotations change
  useEffect(() => {
    if (!state.annotatorId) return;
    saveToLocalStorage(state);
    setLastSavedAt(Date.now());
    const t = setTimeout(doServerSync, SYNC_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [state.annotations, state.annotatorId, doServerSync]);

  return { lastSavedAt, serverStatus, saveNow };
}
