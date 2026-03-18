export function ContextDisplay({ context }) {
  const lines = context.split('\n');
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-1 max-h-56 overflow-y-auto scrollbar-thin">
      {lines.map((line, i) => {
        const isLabel =
          line.startsWith('Therapist:') ||
          line.startsWith('Client:') ||
          line.startsWith('Counselor:') ||
          line.startsWith('Patient:');
        if (isLabel) {
          return (
            <p key={i} className="context-turn text-sm font-semibold text-slate-800">
              {line}
            </p>
          );
        }
        return (
          <p key={i} className="context-turn text-sm text-slate-600">
            {line}
          </p>
        );
      })}
    </div>
  );
}
