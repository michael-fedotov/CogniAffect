const CARD_COLORS = {
  A: 'border-blue-200 bg-blue-50/30',
  B: 'border-purple-200 bg-purple-50/30',
  C: 'border-teal-200 bg-teal-50/30',
};

const BADGE_COLORS = {
  A: 'bg-blue-600 text-white',
  B: 'bg-purple-600 text-white',
  C: 'bg-teal-600 text-white',
};

export function ResponseCard({ label, text }) {
  return (
    <div
      className={`rounded-xl border-2 p-4 ${CARD_COLORS[label] ?? 'border-slate-200 bg-white'}`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${BADGE_COLORS[label] ?? 'bg-slate-600 text-white'}`}
        >
          {label}
        </span>
        <p className="text-sm text-slate-700 leading-relaxed">{text}</p>
      </div>
    </div>
  );
}
