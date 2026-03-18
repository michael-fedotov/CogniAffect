import { generateCSV } from '../../utils/csv/generateCsv';
import { downloadFile } from '../../utils/file/downloadFile';

export function Header({ state, lastSavedAt, serverStatus, onSaveNow }) {

  function handleDownloadCSV() {
    const csv = generateCSV(state);
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    downloadFile(
      csv,
      `annotations_${state.annotatorId}_${ts}.csv`,
      'text/csv;charset=utf-8;',
    );
  }

  const savedLabel = lastSavedAt
    ? `Saved ${new Date(lastSavedAt).toLocaleTimeString()}`
    : 'Not saved yet';

  return (
    <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
      {/* Logo + ID */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
          <svg
            className="w-4 h-4 text-white"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
            />
          </svg>
        </div>
        <div className="min-w-0">
          <h1 className="text-sm font-bold text-slate-800 break-words">
            BWS Empathy Annotation
          </h1>
          <p className="text-xs text-slate-500">
            ID:{' '}
            <span className="font-mono font-semibold text-indigo-600">
              {state.annotatorId}
            </span>
          </p>
        </div>
      </div>

      {/* Sync status */}
      <div className="hidden sm:flex items-center gap-3 text-xs">
        <span className="flex items-center gap-1.5 text-slate-400">
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"
            />
          </svg>
          {savedLabel}
        </span>

        {serverStatus === 'synced' && (
          <span className="flex items-center gap-1 text-emerald-600 font-medium">
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clipRule="evenodd"
              />
            </svg>
            Server synced
          </span>
        )}

        {serverStatus === 'syncing' && (
          <span className="flex items-center gap-1 text-indigo-500 font-medium">
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Syncing…
          </span>
        )}

        {serverStatus === 'waking' && (
          <span
            className="flex items-center gap-1 text-amber-600 font-medium"
            title="Server is waking up (Render free tier). This may take 30–60 seconds."
          >
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Waking up server…
          </span>
        )}

        {serverStatus === 'offline' && (
          <span
            className="flex items-center gap-1 text-amber-500 font-medium"
            title="Server not reachable — data saved locally"
          >
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            Local only
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onSaveNow}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 text-xs font-medium hover:bg-slate-50 transition-all"
        >
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"
            />
          </svg>
          Save
        </button>
        <button
          onClick={handleDownloadCSV}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 transition-all"
        >
          <svg
            className="w-3.5 h-3.5"
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
          CSV
        </button>
      </div>
    </header>
  );
}
