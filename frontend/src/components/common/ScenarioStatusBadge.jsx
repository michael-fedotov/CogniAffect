export function ScenarioStatusBadge({ status }) {
  if (status === 'complete') {
    return (
      <span
        className="flex-shrink-0 w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center"
        aria-label="Complete"
      >
        <svg
          className="w-3 h-3 text-white"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </span>
    );
  }

  if (status === 'partial') {
    return (
      <span
        className="flex-shrink-0 w-5 h-5 rounded-full bg-amber-400 flex items-center justify-center"
        aria-label="In progress"
      >
        <span className="w-2 h-2 rounded-full bg-white" />
      </span>
    );
  }

  return (
    <span
      className="flex-shrink-0 w-5 h-5 rounded-full border-2 border-slate-300 bg-white"
      aria-label="Not started"
    />
  );
}
