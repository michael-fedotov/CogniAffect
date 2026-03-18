import { isAnnotationComplete } from '../utils/annotation/completion';
import { generateCSV } from '../utils/csv/generateCsv';
import { downloadFile } from '../utils/file/downloadFile';
import { apiUrl } from '../utils/constants/api';
import { ACTION_TYPES } from '../state/annotationActionTypes';

export function CompletionScreen({ state, dispatch }) {
  const { scenarios, annotations, annotatorId } = state;
  const completedCount = scenarios.filter((s) =>
    isAnnotationComplete(annotations[s.scenario_id]),
  ).length;

  const totalTime = Object.values(annotations).reduce((sum, ann) => {
    if (ann.startTime && ann.endTime) {
      return sum + Math.round((ann.endTime - ann.startTime) / 1000);
    }
    return sum;
  }, 0);
  const mins = Math.floor(totalTime / 60);
  const secs = totalTime % 60;

  function handleDownloadCSV() {
    const csv = generateCSV(state);
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    downloadFile(
      csv,
      `annotations_${annotatorId}_${ts}.csv`,
      'text/csv;charset=utf-8;',
    );
  }

  function handleDownloadJSON() {
    const data = {
      annotatorId,
      exportTimestamp: new Date().toISOString(),
      annotations,
      shuffleMaps: state.shuffleMaps,
    };
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    downloadFile(
      JSON.stringify(data, null, 2),
      `annotations_${annotatorId}_${ts}.json`,
      'application/json',
    );
  }

  function handleReviewAnnotations() {
    dispatch({
      type: ACTION_TYPES.START_SESSION,
      annotatorId: state.annotatorId,
      scenarios: state.scenarios,
      existingSession: {
        annotations: state.annotations,
        shuffleMaps: state.shuffleMaps,
        currentScenarioIndex: 0,
      },
    });
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-indigo-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Hero */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-emerald-500 shadow-lg mb-4">
            <svg
              className="w-10 h-10 text-white"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-slate-800">Annotation Complete!</h1>
          <p className="text-slate-500 mt-1.5 text-sm">
            Thank you for your contribution to this research study
          </p>
        </div>

        <div className="bg-white rounded-2xl shadow-xl border border-slate-100 p-6 space-y-6">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-indigo-50 rounded-xl p-3">
              <p className="text-2xl font-bold text-indigo-700">{completedCount}</p>
              <p className="text-xs text-indigo-500 mt-0.5">Completed</p>
            </div>
            <div className="bg-slate-50 rounded-xl p-3">
              <p className="text-2xl font-bold text-slate-700">{scenarios.length}</p>
              <p className="text-xs text-slate-500 mt-0.5">Total</p>
            </div>
            <div className="bg-emerald-50 rounded-xl p-3">
              <p className="text-2xl font-bold text-emerald-700">
                {mins}m {secs}s
              </p>
              <p className="text-xs text-emerald-500 mt-0.5">Time spent</p>
            </div>
          </div>

          {/* Download actions */}
          <div className="space-y-3">
            <button
              onClick={handleDownloadCSV}
              className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-indigo-600 text-white font-semibold hover:bg-indigo-700 transition-all shadow-md"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              Download My Annotations (CSV)
            </button>

            <a
              href={apiUrl(`/api/export/csv/${encodeURIComponent(annotatorId)}`)}
              className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-xl border-2 border-emerald-300 bg-emerald-50 text-emerald-700 font-semibold hover:bg-emerald-100 transition-all"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M5 12h14M12 5l7 7-7 7"
                />
              </svg>
              Download from Server (CSV)
            </a>

            <button
              onClick={handleDownloadJSON}
              className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold hover:bg-slate-50 transition-all"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              Download Archive (JSON)
            </button>
          </div>

          {/* Secondary actions */}
          <div className="flex gap-3">
            <button
              onClick={handleReviewAnnotations}
              className="flex-1 px-4 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 text-sm font-medium hover:bg-slate-50 transition-all"
            >
              Review Annotations
            </button>
            <button
              onClick={() => dispatch({ type: ACTION_TYPES.RESET })}
              className="flex-1 px-4 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 text-sm font-medium hover:bg-slate-50 transition-all"
            >
              New Session
            </button>
          </div>

          <p className="text-xs text-slate-400 text-center">
            Your annotations are saved in the server database and locally in this
            browser.
            <br />
            The researcher can collect all data at{' '}
            <a
              href={apiUrl('/admin')}
              className="text-indigo-400 hover:underline font-mono"
              target="_blank"
              rel="noopener noreferrer"
            >
              /admin
            </a>
            .
          </p>
        </div>
      </div>
    </div>
  );
}
