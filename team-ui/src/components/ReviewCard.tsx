import type { KnowledgeUnit, Selection } from "../types";
import { DomainTags } from "./DomainTags";
import { timeAgo } from "../utils";

interface Props {
  unit: KnowledgeUnit;
  selection: Selection;
  onSelect: (s: Selection) => void;
}

const CARD_STYLES: Record<string, string> = {
  neutral: "border-gray-200 bg-white",
  approve: "border-green-300 bg-green-50",
  reject: "border-red-300 bg-red-50",
  skip: "border-slate-400 bg-slate-50",
};

const ACTION_BOX_STYLES: Record<string, string> = {
  neutral: "bg-indigo-50 border-indigo-500 text-indigo-500",
  approve: "bg-green-50 border-green-500 text-green-600",
  reject: "bg-red-50 border-red-500 text-red-600",
  skip: "bg-slate-50 border-slate-400 text-slate-500",
};

function confidenceColor(c: number): string {
  if (c < 0.3) return "text-red-600";
  if (c < 0.5) return "text-amber-600";
  if (c < 0.7) return "text-yellow-500";
  return "text-green-600";
}

export function ReviewCard({ unit, selection, onSelect }: Props) {
  const cardStyle = CARD_STYLES[selection ?? "neutral"];

  return (
    <div
      className={`border-2 rounded-lg p-6 max-w-xl mx-auto transition-all duration-200 ${cardStyle}`}
    >
      <div className="flex items-center justify-between mb-3">
        <DomainTags domains={unit.domain} variant={selection} />
        <span className="text-xs text-gray-400">
          {timeAgo(unit.evidence.first_observed)}
        </span>
      </div>

      <h2 className="text-lg font-semibold text-gray-900 mb-2">
        {unit.insight.summary}
      </h2>

      <p className="text-gray-600 mb-3 leading-relaxed">
        {unit.insight.detail}
      </p>

      <div className={`border-l-3 rounded-r-lg px-4 py-3 mb-6 ${ACTION_BOX_STYLES[selection ?? "neutral"]}`}>
        <span className="text-xs font-semibold uppercase tracking-wide">
          Action
        </span>
        <p className="text-gray-800 text-sm mt-1">{unit.insight.action}</p>
      </div>

      <div className="flex gap-4 text-sm text-gray-500 mb-6">
        <span>
          Confidence: <strong className={confidenceColor(unit.evidence.confidence)}>{unit.evidence.confidence.toFixed(2)}</strong>
        </span>
        <span>
          Confirmations: <strong className="text-gray-800">{unit.evidence.confirmations}</strong>
        </span>
      </div>

      <div className="flex gap-3 justify-center">
        <button
          onClick={() => onSelect(selection === "reject" ? null : "reject")}
          className={`px-8 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 ${
            selection === "reject"
              ? "bg-red-600 text-white ring-3 ring-red-200"
              : selection === "approve"
                ? "bg-red-100 text-red-600 opacity-40"
                : "bg-red-100 text-red-600"
          }`}
        >
          ← Reject
        </button>
        <button
          onClick={() => onSelect(selection === "approve" ? null : "approve")}
          className={`px-8 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 ${
            selection === "approve"
              ? "bg-green-600 text-white ring-3 ring-green-200"
              : selection === "reject"
                ? "bg-green-100 text-green-600 opacity-40"
                : "bg-green-100 text-green-600"
          }`}
        >
          Approve →
        </button>
      </div>

      <p className={`text-center mt-2 text-xs ${
        selection === "approve"
          ? "text-green-600 font-medium"
          : selection === "reject"
            ? "text-red-600 font-medium"
            : "text-gray-400"
      }`}>
        {selection
          ? "Press space to confirm · Esc to cancel"
          : "Use arrow keys to select, space to confirm"}
      </p>
    </div>
  );
}
