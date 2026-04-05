export function ContextDisplay({ context }) {
  const lines = context.split('\n');
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-1 max-h-56 overflow-y-auto scrollbar-thin">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        
        // Skip empty lines
        if (!trimmed) return null;
        
        const isClientLabel = trimmed.startsWith('Client:') || trimmed.startsWith('Patient:');
        const isTherapistLabel = trimmed.startsWith('Therapist:') || trimmed.startsWith('Counselor:');
        
        if (isClientLabel) {
          return (
            <p key={i} className="context-turn text-sm font-semibold text-purple-700">
              {trimmed}
            </p>
          );
        }
        
        if (isTherapistLabel) {
          return (
            <p key={i} className="context-turn text-sm text-slate-600">
              {trimmed}
            </p>
          );
        }
        
        return (
          <p key={i} className="context-turn text-sm text-slate-600">
            {trimmed}
          </p>
        );
      })}
    </div>
  );
}
