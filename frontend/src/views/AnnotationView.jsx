import { useState, useEffect, useRef } from 'react';
import { Header } from '../components/layout/Header';
import { Sidebar } from '../components/layout/Sidebar';
import { MobileSidebar } from '../components/layout/MobileSidebar';
import { ScenarioPanel } from '../features/annotation/ScenarioPanel';
import { useAutoSync } from '../hooks/useAutoSync';
import { ACTION_TYPES } from '../state/annotationActionTypes';

export function AnnotationView({ state, dispatch }) {
  const [showMobileSidebar, setShowMobileSidebar] = useState(false);
  const { lastSavedAt, serverStatus, saveNow } = useAutoSync(state, dispatch);

  // Record startTime for the initial scenario when the view mounts
  useEffect(() => {
    const scenario = state.scenarios[state.currentScenarioIndex];
    if (!scenario) return;
    const ann = state.annotations[scenario.scenario_id] || {};
    if (!ann.startTime) {
      dispatch({
        type: ACTION_TYPES.UPDATE_ANNOTATION,
        scenarioId: scenario.scenario_id,
        field: 'startTime',
        value: Date.now(),
      });
    }
  }, [state.currentScenarioIndex]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col h-screen overflow-hidden min-h-0">
      <Header
        state={state}
        lastSavedAt={lastSavedAt}
        serverStatus={serverStatus}
        onSaveNow={saveNow}
      />

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Desktop sidebar */}
        <div className="sidebar-desktop hidden md:flex">
          <Sidebar state={state} dispatch={dispatch} />
        </div>

        {/* Mobile sidebar overlay */}
        {showMobileSidebar && (
          <MobileSidebar
            state={state}
            dispatch={dispatch}
            onClose={() => setShowMobileSidebar(false)}
          />
        )}

        {/* Main content */}
        <main className="flex-1 min-h-0 min-w-0 overflow-x-hidden overflow-y-auto scrollbar-thin">
          {/* Mobile top bar */}
          <div className="md:hidden flex items-center justify-between bg-white border-b border-slate-200 px-4 py-2.5">
            <button
              onClick={() => setShowMobileSidebar(true)}
              className="flex items-center gap-2 text-sm text-slate-600 font-medium"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
              All Scenarios
            </button>
            <span className="text-sm text-slate-500 font-medium">
              {state.currentScenarioIndex + 1} / {state.scenarios.length}
            </span>
          </div>

          <div className="max-w-3xl w-full min-w-0 mx-auto px-4 py-6">
            <ScenarioPanel state={state} dispatch={dispatch} />
          </div>
        </main>
      </div>
    </div>
  );
}
