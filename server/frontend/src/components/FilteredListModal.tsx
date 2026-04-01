import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { StatusBadge } from "./StatusBadge";
import { DomainTags } from "./DomainTags";
import type { ReviewItem } from "../types";

export interface ListFilter {
  title: string;
  domain?: string;
  confidence_min?: number;
  confidence_max?: number;
  status?: string;
}

interface Props {
  filter: ListFilter;
  onClose: () => void;
  onSelectUnit: (unitId: string) => void;
}

function confidenceLabel(c: number): string {
  return c.toFixed(2);
}

const MODAL_TITLE_ID = "filtered-list-title";

export function FilteredListModal({ filter, onClose, onSelectUnit }: Props) {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let ignore = false;
    api
      .listUnits({
        domain: filter.domain,
        confidence_min: filter.confidence_min,
        confidence_max: filter.confidence_max,
        status: filter.status,
      })
      .then((data) => {
        if (!ignore) setItems(data);
      })
      .catch((err) => {
        if (ignore) return;
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load knowledge units.");
        }
      });
    return () => {
      ignore = true;
    };
  }, [filter.domain, filter.confidence_min, filter.confidence_max, filter.status]);

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
        aria-labelledby={MODAL_TITLE_ID}
        tabIndex={-1}
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col outline-none"
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 id={MODAL_TITLE_ID} className="text-lg font-semibold text-gray-900">
            {filter.title}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <p className="text-red-600 text-sm text-center py-4">{error}</p>
          )}

          {!items && !error && (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 animate-pulse bg-gray-100 rounded-lg" />
              ))}
            </div>
          )}

          {items && items.length === 0 && (
            <p className="text-gray-400 text-sm text-center py-8">
              No knowledge units found.
            </p>
          )}

          {items && items.length > 0 && (
            <div className="space-y-2">
              {items.map((item) => (
                <button
                  key={item.knowledge_unit.id}
                  className="w-full text-left p-3 rounded-lg border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50/50 transition-colors"
                  onClick={() => onSelectUnit(item.knowledge_unit.id)}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <StatusBadge status={item.status} />
                    <span className="text-sm font-medium text-gray-900 truncate">
                      {item.knowledge_unit.insight.summary}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <DomainTags domains={item.knowledge_unit.domain} />
                    <span className="text-xs text-gray-400 ml-auto shrink-0">
                      {confidenceLabel(item.knowledge_unit.evidence.confidence)}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
