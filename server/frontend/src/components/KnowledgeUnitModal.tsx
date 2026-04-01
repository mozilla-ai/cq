import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { StatusBadge } from "./StatusBadge";
import { DomainTags } from "./DomainTags";
import { timeAgo } from "../utils";
import type { ReviewItem } from "../types";

interface Props {
  unitId: string;
  onClose: () => void;
}

function confidenceColor(c: number): string {
  if (c < 0.3) return "text-red-600";
  if (c < 0.5) return "text-amber-600";
  if (c < 0.7) return "text-yellow-500";
  return "text-green-600";
}

const MODAL_TITLE_ID = "ku-modal-title";

export function KnowledgeUnitModal({ unitId, onClose }: Props) {
  const [item, setItem] = useState<ReviewItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let ignore = false;
    api
      .getUnit(unitId)
      .then((data) => {
        if (!ignore) setItem(data);
      })
      .catch((err) => {
        if (ignore) return;
        if (err instanceof ApiError && err.status === 404) {
          setError("Knowledge unit not found.");
        } else {
          setError("Failed to load knowledge unit.");
        }
      });
    return () => {
      ignore = true;
    };
  }, [unitId]);

  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={item ? MODAL_TITLE_ID : undefined}
        tabIndex={-1}
        className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto outline-none"
      >
        {error && (
          <div className="p-6 text-center">
            <p className="text-red-600 text-sm">{error}</p>
            <button
              onClick={onClose}
              className="mt-3 text-sm text-gray-500 hover:text-gray-700"
            >
              Close
            </button>
          </div>
        )}

        {!item && !error && (
          <div className="p-6 space-y-3">
            <div className="h-4 w-32 animate-pulse bg-gray-200 rounded" />
            <div className="h-6 w-48 animate-pulse bg-gray-200 rounded" />
            <div className="h-16 w-full animate-pulse bg-gray-200 rounded" />
          </div>
        )}

        {item && (
          <div className="p-6 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <h2 id={MODAL_TITLE_ID} className="text-lg font-semibold text-gray-900">
                {item.knowledge_unit.insight.summary}
              </h2>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none shrink-0"
                aria-label="Close"
              >
                &times;
              </button>
            </div>

            <div className="flex items-center gap-2">
              <StatusBadge status={item.status} />
              {item.reviewed_by && (
                <span className="text-xs text-gray-500">
                  by {item.reviewed_by}
                </span>
              )}
              {item.reviewed_at && (
                <span className="text-xs text-gray-400">
                  {timeAgo(item.reviewed_at)}
                </span>
              )}
            </div>

            <DomainTags domains={item.knowledge_unit.domain} />

            <p className="text-gray-600 leading-relaxed">
              {item.knowledge_unit.insight.detail}
            </p>

            <div className="border-l-3 rounded-r-lg px-4 py-3 bg-indigo-50 border-indigo-500">
              <span className="text-xs font-semibold uppercase tracking-wide text-indigo-500">
                Action
              </span>
              <p className="text-gray-800 text-sm mt-1">
                {item.knowledge_unit.insight.action}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 uppercase">Confidence</span>
                <p className={`font-semibold ${confidenceColor(item.knowledge_unit.evidence.confidence)}`}>
                  {item.knowledge_unit.evidence.confidence.toFixed(2)}
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 uppercase">Confirmations</span>
                <p className="font-semibold text-gray-800">
                  {item.knowledge_unit.evidence.confirmations}
                </p>
              </div>
            </div>

            {(item.knowledge_unit.context.languages.length > 0 ||
              item.knowledge_unit.context.frameworks.length > 0) && (
              <div className="text-sm text-gray-500">
                {item.knowledge_unit.context.languages.length > 0 && (
                  <span>
                    Languages: {item.knowledge_unit.context.languages.join(", ")}
                  </span>
                )}
                {item.knowledge_unit.context.languages.length > 0 &&
                  item.knowledge_unit.context.frameworks.length > 0 && (
                    <span className="mx-2">&middot;</span>
                  )}
                {item.knowledge_unit.context.frameworks.length > 0 && (
                  <span>
                    Frameworks: {item.knowledge_unit.context.frameworks.join(", ")}
                  </span>
                )}
              </div>
            )}

            <div className="flex items-center justify-between text-xs text-gray-400 pt-2 border-t border-gray-100">
              <span className="font-mono">{item.knowledge_unit.id}</span>
              <span>{timeAgo(item.knowledge_unit.evidence.first_observed)}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
