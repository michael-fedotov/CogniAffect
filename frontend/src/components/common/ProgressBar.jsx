export function ProgressBar({ current, total }) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="text-sm font-medium text-slate-600 whitespace-nowrap flex-shrink-0">
        {current} / {total} complete
      </span>
      <div className="flex-1 min-w-0 bg-slate-200 rounded-full h-2">
        <div
          className="bg-indigo-600 h-2 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <span className="text-sm font-semibold text-indigo-600 whitespace-nowrap flex-shrink-0">
        {pct}%
      </span>
    </div>
  );
}
