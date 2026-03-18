import { ProgressBar } from '../common/ProgressBar';
import { ScenarioStatusBadge } from '../common/ScenarioStatusBadge';
import { isAnnotationComplete } from '../../utils/annotation/completion';
import { ACTION_TYPES } from '../../state/annotationActionTypes';

function getScenarioStatus(ann) {
  if (!ann) return 'none';
  if (isAnnotationComplete(ann)) return 'complete';
  if (
    ann.cognitiveMost ||
    ann.cognitiveLeast ||
    ann.affectiveMost ||
    ann.affectiveLeast
  )
    return 'partial';
  return 'none';
}

export function Sidebar({ state, dispatch }) {
  const { scenarios, annotations, currentScenarioIndex } = state;
  const completedCount = scenarios.filter((s) =>
    isAnnotationComplete(annotations[s.scenario_id]),
  ).length;

  return (
    <aside className="w-72 flex-shrink-0 flex flex-col bg-white border-r border-slate-200 min-w-0">
      <div className="p-4 border-b border-slate-200 min-w-0">
        <p className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
          Scenarios
        </p>
        <ProgressBar current={completedCount} total={scenarios.length} />
      </div>

      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin py-2 min-w-0"
        aria-label="Scenario list"
      >
        {scenarios.map((s, idx) => {
          const status = getScenarioStatus(annotations[s.scenario_id]);
          const isCurrent = idx === currentScenarioIndex;
          return (
            <button
              key={s.scenario_id}
              onClick={() => dispatch({ type: ACTION_TYPES.NAVIGATE, index: idx })}
              className={`w-full text-left flex items-center gap-3 px-4 py-2.5 text-sm transition-colors min-w-0
                ${
                  isCurrent
                    ? 'bg-indigo-50 text-indigo-700 font-semibold border-r-2 border-indigo-600'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-800'
                }`}
              aria-current={isCurrent ? 'page' : undefined}
            >
              <ScenarioStatusBadge status={status} />
              <span className="break-words">{s.scenario_id.replace('_', ' ')}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
