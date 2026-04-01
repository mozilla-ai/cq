import type { Selection } from "../types";

interface Props {
  selection: Selection;
  onSelect: (s: Selection) => void;
  onConfirm: () => void;
  disabled: boolean;
}

export function ReviewActions({ selection, onSelect, onConfirm, disabled }: Props) {
  return (
    <div className="max-w-xl mx-auto mt-4 hidden pointer-fine:flex flex-col items-center gap-3">
      <div className="flex gap-3 justify-center">
        <button
          onClick={() => {
            if (selection === "reject") { onConfirm(); } else { onSelect("reject"); }
          }}
          disabled={disabled}
          className={`px-8 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 disabled:opacity-50 ${
            selection === "reject"
              ? "bg-red-600 text-white ring-3 ring-red-200"
              : selection
                ? "bg-red-100 text-red-600 opacity-40"
                : "bg-red-100 text-red-600"
          }`}
        >
          {selection === "reject" ? "Confirm Reject" : "\u2190 Reject"}
        </button>
        <button
          onClick={() => {
            if (selection === "skip") { onConfirm(); } else { onSelect("skip"); }
          }}
          disabled={disabled}
          className={`px-6 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 disabled:opacity-50 ${
            selection === "skip"
              ? "bg-slate-600 text-white ring-3 ring-slate-200"
              : selection
                ? "bg-slate-100 text-slate-600 opacity-40"
                : "bg-slate-100 text-slate-600"
          }`}
        >
          {selection === "skip" ? "Confirm Skip" : "\u2191\u2193 Skip"}
        </button>
        <button
          onClick={() => {
            if (selection === "approve") { onConfirm(); } else { onSelect("approve"); }
          }}
          disabled={disabled}
          className={`px-8 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 disabled:opacity-50 ${
            selection === "approve"
              ? "bg-green-600 text-white ring-3 ring-green-200"
              : selection
                ? "bg-green-100 text-green-600 opacity-40"
                : "bg-green-100 text-green-600"
          }`}
        >
          {selection === "approve" ? "Confirm Approve" : "Approve \u2192"}
        </button>
      </div>
      <p className={`text-center text-xs ${
        selection ? "text-gray-500 font-medium" : "text-gray-400"
      }`}>
        {selection
          ? "Click again or press Space/Enter to confirm \u00b7 Esc to cancel"
          : "Arrow keys to select \u00b7 Space/Enter to confirm"}
      </p>
    </div>
  );
}
