const SESSION_PREFIX = 'bws_session_';

export function saveToLocalStorage(state) {
  if (!state.annotatorId) return;
  const key = `${SESSION_PREFIX}${state.annotatorId}`;
  const saved = {
    annotatorId: state.annotatorId,
    annotations: state.annotations,
    shuffleMaps: state.shuffleMaps,
    currentScenarioIndex: state.currentScenarioIndex,
    savedAt: Date.now(),
  };
  try {
    localStorage.setItem(key, JSON.stringify(saved));
  } catch {
    // Storage quota exceeded or unavailable — fail silently
  }
}

export function loadFromLocalStorage(annotatorId) {
  try {
    const key = `${SESSION_PREFIX}${annotatorId}`;
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearLocalSession(annotatorId) {
  if (!annotatorId) return;
  try {
    localStorage.removeItem(`${SESSION_PREFIX}${annotatorId}`);
  } catch {
    /* ignore */
  }
}

export function findExistingSessions() {
  const sessions = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(SESSION_PREFIX)) {
        const raw = localStorage.getItem(key);
        if (raw) {
          const data = JSON.parse(raw);
          sessions.push(data);
        }
      }
    }
  } catch {
    // localStorage unavailable
  }
  return sessions;
}
