export function RadioGroup({ name, options, value, onChange, error }) {
  return (
    <div
      className={`flex flex-wrap gap-2 min-w-0 ${
        error ? 'p-2 rounded-lg border-2 border-red-400 bg-red-50' : ''
      }`}
      role="radiogroup"
    >
      {options.map((opt) => (
        <label
          key={opt.value}
          className={`radio-option flex items-center gap-2 cursor-pointer px-4 py-2.5 rounded-lg border-2 transition-colors select-none
            ${
              value === opt.value
                ? 'border-indigo-600 bg-indigo-50 text-indigo-700 font-semibold'
                : 'border-slate-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/40 text-slate-700'
            }`}
        >
          <input
            type="radio"
            name={name}
            value={opt.value}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
            className="sr-only"
          />
          <span
            className={`w-4 h-4 rounded-full border-2 flex-shrink-0 flex items-center justify-center
              ${value === opt.value ? 'border-indigo-600 bg-indigo-600' : 'border-slate-300 bg-white'}`}
          >
            {value === opt.value && (
              <span className="w-1.5 h-1.5 rounded-full bg-white" />
            )}
          </span>
          <span>{opt.label}</span>
        </label>
      ))}
    </div>
  );
}
