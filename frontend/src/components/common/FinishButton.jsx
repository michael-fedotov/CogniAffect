import { useState } from 'react';
import { isAnnotationComplete } from '../../utils/annotation/completion';
import { ACTION_TYPES } from '../../state/annotationActionTypes';

export function FinishButton({ state, dispatch }) {
  const [showModal, setShowModal] = useState(false);
  const { scenarios, annotations } = state;

  const incomplete = scenarios.filter(
    (s) => !isAnnotationComplete(annotations[s.scenario_id]),
  );
  const completedCount = scenarios.length - incomplete.length;

  function handleFinish() {
    if (incomplete.length > 0) {
      setShowModal(true);
    } else {
      dispatch({ type: ACTION_TYPES.COMPLETE });
    }
  }

  return (
    <>
      <button
        onClick={handleFinish}
        className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-600 text-white font-medium text-sm hover:bg-emerald-700 transition-all shadow-sm"
      >
        Finish &amp; Export
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </button>

      {showModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                <svg
                  className="w-5 h-5 text-amber-600"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-bold text-slate-800">Incomplete Annotations</h3>
            </div>

            <p className="text-sm text-slate-600">
              You have completed{' '}
              <strong>
                {completedCount} of {scenarios.length}
              </strong>{' '}
              scenarios. The following scenarios are incomplete:
            </p>

            <ul className="space-y-1 max-h-48 overflow-y-auto">
              {incomplete.map((s) => (
                <li
                  key={s.scenario_id}
                  className="flex items-center gap-2 text-sm text-slate-700"
                >
                  <span className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0" />
                  {s.scenario_id.replace('_', ' ')}
                </li>
              ))}
            </ul>

            <p className="text-sm text-slate-500">
              Only completed annotations will be exported to CSV.
            </p>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setShowModal(false)}
                className="flex-1 px-4 py-2.5 rounded-lg border-2 border-slate-200 text-slate-700 font-medium text-sm hover:bg-slate-50 transition-all"
              >
                Go Back
              </button>
              <button
                onClick={() => {
                  setShowModal(false);
                  dispatch({ type: ACTION_TYPES.COMPLETE });
                }}
                className="flex-1 px-4 py-2.5 rounded-lg bg-emerald-600 text-white font-medium text-sm hover:bg-emerald-700 transition-all"
              >
                Export Anyway
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
