import { useState, useEffect, useRef } from 'react';
import { generateAnnotatorId } from '../utils/annotation/annotatorId';
import { isAnnotationComplete } from '../utils/annotation/completion';
import {
  findExistingSessions,
  loadFromLocalStorage,
} from '../utils/storage/localSessionStorage';
import { loadSessionFromServer } from '../utils/api/annotationApi';
import { ACTION_TYPES } from '../state/annotationActionTypes';
import { apiUrl } from '../utils/constants/api';

export function WelcomeScreen({ dispatch }) {
  const [annotatorId, setAnnotatorId] = useState('');
  const [scenarios, setScenarios] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [existingSessions, setExistingSessions] = useState([]);
  const [loadingAuto, setLoadingAuto] = useState(true);
  const [selectedResume, setSelectedResume] = useState(null);
  const [starting, setStarting] = useState(false);
  const [serverWakingUp, setServerWakingUp] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    setExistingSessions(findExistingSessions());

    fetch(apiUrl('/scenarios.json'))
      .then((r) => {
        if (!r.ok) throw new Error('Not found');
        return r.json();
      })
      .then((data) => {
        setScenarios(data);
        setLoadingAuto(false);
      })
      .catch(() => setLoadingAuto(false));
  }, []);

  function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result);
        if (!data.scenarios || !Array.isArray(data.scenarios)) {
          throw new Error('Invalid format');
        }
        setScenarios(data);
        setLoadError('');
      } catch {
        setLoadError('Invalid JSON file. Please select a valid scenarios.json file.');
      }
    };
    reader.readAsText(file);
  }

  async function handleStart(resumeSession) {
    const id = annotatorId.trim() || generateAnnotatorId();
    if (!scenarios) {
      setLoadError('Please load a scenarios.json file first.');
      return;
    }
    setStarting(true);
    setServerWakingUp(false);

    let existingSession = resumeSession || loadFromLocalStorage(id);
    const serverSession = await loadSessionFromServer(id, {
      onWakingUp: () => setServerWakingUp(true),
    });
    setServerWakingUp(false);

    if (serverSession?.savedAt) {
      const localSavedAt = existingSession?.savedAt ?? 0;
      if (serverSession.savedAt > localSavedAt) {
        existingSession = serverSession;
      }
    }

    dispatch({
      type: ACTION_TYPES.START_SESSION,
      annotatorId: id,
      scenarios: scenarios.scenarios,
      existingSession,
    });
  }

  function handleResumeSession(session) {
    setAnnotatorId(session.annotatorId);
    setSelectedResume(session);
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-violet-50 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Logo / Title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-indigo-600 shadow-lg mb-4">
            <svg
              className="w-8 h-8 text-white"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-slate-800">BWS Empathy Annotation</h1>
          <p className="text-slate-500 mt-1.5 text-sm">
            Best-Worst Scaling Study on Therapeutic Dialogue
          </p>
        </div>

        <div className="bg-white rounded-2xl shadow-xl border border-slate-100 p-6 space-y-6">
          {/* Resume existing sessions */}
          {existingSessions.length > 0 && (
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-3">
                Resume Session
              </p>
              <div className="space-y-2">
                {existingSessions.map((session) => {
                  const completedCount = Object.values(
                    session.annotations || {},
                  ).filter((a) => isAnnotationComplete(a)).length;
                  return (
                    <button
                      key={session.annotatorId}
                      onClick={() => handleResumeSession(session)}
                      className={`w-full text-left flex items-center justify-between px-4 py-3 rounded-xl border-2 transition-all
                        ${
                          selectedResume?.annotatorId === session.annotatorId
                            ? 'border-indigo-500 bg-indigo-50'
                            : 'border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/40'
                        }`}
                    >
                      <div>
                        <p className="font-semibold text-sm text-slate-800 font-mono">
                          {session.annotatorId}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {completedCount} scenario
                          {completedCount !== 1 ? 's' : ''} completed
                          {session.savedAt
                            ? ` · Saved ${new Date(session.savedAt).toLocaleString()}`
                            : ''}
                        </p>
                      </div>
                      {selectedResume?.annotatorId === session.annotatorId && (
                        <svg
                          className="w-5 h-5 text-indigo-600"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path
                            fillRule="evenodd"
                            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                            clipRule="evenodd"
                          />
                        </svg>
                      )}
                    </button>
                  );
                })}
              </div>
              <div className="relative my-4">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-200" />
                </div>
                <div className="relative flex justify-center">
                  <span className="bg-white px-3 text-xs text-slate-400">
                    or start new
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Annotator ID */}
          <div>
            <label
              htmlFor="annotator-id"
              className="block text-sm font-semibold text-slate-700 mb-1.5"
            >
              Annotator ID
            </label>
            <input
              id="annotator-id"
              type="text"
              value={annotatorId}
              onChange={(e) => {
                setAnnotatorId(e.target.value);
                setSelectedResume(null);
              }}
              placeholder="e.g., ANNO_001 (leave blank to auto-generate)"
              className="w-full rounded-xl border-2 border-slate-200 px-4 py-2.5 text-sm font-mono text-slate-700 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            />
          </div>

          {/* Load scenarios */}
          <div>
            <p className="text-sm font-semibold text-slate-700 mb-2">Scenarios Data</p>
            {loadingAuto ? (
              <div className="flex items-center gap-2 text-sm text-slate-500 py-2">
                <svg
                  className="w-4 h-4 animate-spin text-indigo-500"
                  fill="none"
                  viewBox="0 0 24 24"
                >
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
                Loading scenarios.json…
              </div>
            ) : scenarios ? (
              <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2.5">
                <svg
                  className="w-4 h-4 text-emerald-500 flex-shrink-0"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
                <div>
                  <p className="text-sm font-semibold text-emerald-700">
                    Loaded successfully
                  </p>
                  <p className="text-xs text-emerald-600">
                    {scenarios.scenarios.length} scenario
                    {scenarios.scenarios.length !== 1 ? 's' : ''} ready
                  </p>
                </div>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="ml-auto text-xs text-emerald-600 underline hover:text-emerald-700"
                >
                  Replace
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 text-amber-700 text-sm">
                  <svg
                    className="w-4 h-4 flex-shrink-0 mt-0.5"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Could not auto-load scenarios.json. Please upload it manually.
                </div>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 border-dashed border-slate-300 hover:border-indigo-400 hover:bg-indigo-50/40 text-slate-600 text-sm font-medium transition-all"
                >
                  <svg
                    className="w-5 h-5 text-slate-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                    />
                  </svg>
                  Upload scenarios.json
                </button>
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              onChange={handleFileUpload}
              className="hidden"
              aria-label="Upload scenarios JSON file"
            />
            {loadError && (
              <p className="mt-2 text-sm text-red-600" role="alert">
                {loadError}
              </p>
            )}
          </div>

          {serverWakingUp && (
            <div className="flex items-center gap-2 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-amber-800 text-sm">
              <svg
                className="w-4 h-4 animate-spin flex-shrink-0"
                fill="none"
                viewBox="0 0 24 24"
              >
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
              Waking up the server… This may take 30–60 seconds on first load.
            </div>
          )}

          {/* Start / Resume button */}
          <button
            onClick={() => handleStart(selectedResume)}
            disabled={!scenarios || starting}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 text-white font-semibold text-base hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md hover:shadow-lg"
          >
            {starting ? (
              <>
                <svg
                  className="w-5 h-5 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
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
                {serverWakingUp ? 'Connecting…' : 'Loading…'}
              </>
            ) : selectedResume ? (
              <>
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
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                Resume Session
              </>
            ) : (
              <>
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
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                Start Annotation
              </>
            )}
          </button>

          {/* Instructions */}
          <details className="text-sm text-slate-500 group">
            <summary className="cursor-pointer font-medium text-slate-600 hover:text-slate-800 list-none flex items-center gap-1">
              <svg
                className="w-4 h-4 transition-transform group-open:rotate-90"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
              Instructions
            </summary>
            <div className="mt-3 space-y-2 pl-5">
              <p>
                For each scenario you will see a therapy dialogue followed by three
                anonymous responses (A, B, C).
              </p>
              <p>
                You will answer <strong>two questions</strong> about each set of
                responses:
              </p>
              <ol className="list-decimal list-inside space-y-1 pl-2">
                <li>
                  <strong>Cognitive Empathy</strong> — which response best/least shows
                  understanding of the client&apos;s perspective
                </li>
                <li>
                  <strong>Affective Empathy</strong> — which response best/least
                  validates the client&apos;s emotional experience
                </li>
              </ol>
              <p>
                Your progress is saved automatically. You can close and resume at any
                time.
              </p>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}
