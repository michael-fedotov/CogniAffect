import { RadioGroup } from '../../components/common/RadioGroup';

export function BWSQuestion({
  dimension,
  title,
  subtitle,
  mostValue,
  leastValue,
  reasoning,
  onMostChange,
  onLeastChange,
  onReasoningChange,
  displayLabels,
}) {
  const sameError = mostValue && leastValue && mostValue === leastValue;
  const radioOptions = displayLabels.map((l) => ({ value: l, label: `Response ${l}` }));
  const headerBg = dimension === 'cognitive' ? 'bg-indigo-600' : 'bg-violet-600';

  return (
    <div
      className="bws-card bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden scroll-mt-24 w-full min-w-0 max-w-full"
      id={`bws-${dimension}`}
    >
      <div className={`px-5 py-3 min-w-0 ${headerBg}`}>
        <h3 className="text-base font-bold text-white break-words">{title}</h3>
        <p className="text-xs text-white/80 mt-0.5 break-words">{subtitle}</p>
      </div>

      <div className="p-5 space-y-5 min-w-0">
        {/* Error slot — always occupies space to prevent layout shift */}
        <div className="bws-error-slot flex flex-col justify-center">
          {sameError && (
            <div
              className="flex items-center gap-2 bg-red-50 border border-red-300 rounded-lg px-4 py-2.5 text-red-700 text-sm"
              role="alert"
              aria-live="polite"
            >
              <svg
                className="w-4 h-4 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
              Please select different responses for MOST and LEAST
            </div>
          )}
        </div>

        {/* MOST */}
        <fieldset>
          <legend className="text-sm font-semibold text-slate-700 mb-2">
            Which response shows this{' '}
            <span className="text-emerald-600 uppercase">MOST</span>?
          </legend>
          <RadioGroup
            name={`${dimension}-most`}
            options={radioOptions}
            value={mostValue}
            onChange={onMostChange}
            error={sameError}
          />
        </fieldset>

        {/* LEAST */}
        <fieldset>
          <legend className="text-sm font-semibold text-slate-700 mb-2">
            Which response shows this{' '}
            <span className="text-red-500 uppercase">LEAST</span>?
          </legend>
          <RadioGroup
            name={`${dimension}-least`}
            options={radioOptions}
            value={leastValue}
            onChange={onLeastChange}
            error={sameError}
          />
        </fieldset>

        {/* Reasoning (optional) */}
        <div>
          <label
            htmlFor={`${dimension}-reasoning`}
            className="block text-sm font-semibold text-slate-700 mb-1.5"
          >
            Reasoning{' '}
            <span className="text-slate-400 font-normal">(optional)</span>
          </label>
          <textarea
            id={`${dimension}-reasoning`}
            value={reasoning}
            onChange={(e) => onReasoningChange(e.target.value)}
            rows={2}
            placeholder="Briefly explain your choice…"
            className="w-full rounded-lg border-2 border-slate-200 px-3 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 resize-none transition-all"
          />
        </div>
      </div>
    </div>
  );
}
