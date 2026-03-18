import { Sidebar } from './Sidebar';

export function MobileSidebar({ state, dispatch, onClose }) {
  return (
    <div
      className="fixed inset-0 z-40 flex md:hidden"
      role="dialog"
      aria-modal="true"
    >
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative z-50 w-72 bg-white h-full shadow-2xl min-w-0">
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <span className="font-bold text-slate-800">Scenarios</span>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100"
            aria-label="Close sidebar"
          >
            <svg
              className="w-5 h-5 text-slate-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        <Sidebar state={state} dispatch={dispatch} />
      </div>
    </div>
  );
}
