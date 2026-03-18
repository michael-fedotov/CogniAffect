import { fetchWithWakeup } from './client';

export async function syncToServer(state, { onWakingUp } = {}) {
  if (!state.annotatorId || !state.scenarios.length) return false;
  try {
    const res = await fetchWithWakeup(
      '/api/sync',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          annotator_id: state.annotatorId,
          session_data: {
            annotations: state.annotations,
            shuffle_maps: state.shuffleMaps,
            current_scenario_index: state.currentScenarioIndex,
            saved_at: Date.now(),
          },
          scenarios: state.scenarios,
        }),
      },
      { onWakingUp },
    );
    return res.ok;
  } catch {
    return false;
  }
}

export async function loadSessionFromServer(annotatorId, { onWakingUp } = {}) {
  try {
    const res = await fetchWithWakeup(
      `/api/session/${encodeURIComponent(annotatorId)}`,
      {},
      { onWakingUp },
    );
    if (!res.ok) return null;
    const data = await res.json();
    if (!data) return null;
    return {
      annotatorId,
      annotations: data.annotations || {},
      shuffleMaps: data.shuffle_maps || {},
      currentScenarioIndex: data.current_scenario_index || 0,
      savedAt: data.saved_at || null,
    };
  } catch {
    return null;
  }
}
