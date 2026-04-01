import { useState, useEffect, useCallback, useRef } from "react";
import { Link, useOutletContext } from "react-router";
import { api, ApiError } from "../api";
import { ReviewCard } from "../components/ReviewCard";
import { ReviewActions } from "../components/ReviewActions";
import { DragIndicators } from "../components/DragIndicators";
import { useCardDrag } from "../hooks/useCardDrag";
import type { ReviewItem, Selection } from "../types";

export function ReviewPage() {
  const { setPendingCount } = useOutletContext<{
    setPendingCount: (n: number) => void;
  }>();

  const [current, setCurrent] = useState<ReviewItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [submitting, setSubmitting] = useState(false);
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);

  const [sessionApproved, setSessionApproved] = useState(0);
  const [sessionRejected, setSessionRejected] = useState(0);

  const skippedIds = useRef(new Set<string>());

  const cardRef = useRef<HTMLDivElement>(null);

  // Fetch 20 items (not 1) so we can skip previously-seen KUs client-side.
  const fetchNext = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSelection(null);
    setConflictMessage(null);
    try {
      const resp = await api.reviewQueue(20, 0);
      const next = resp.items.find(
        (item) => !skippedIds.current.has(item.knowledge_unit.id),
      );
      if (next) {
        setCurrent(next);
        setPendingCount(Math.max(0, resp.total - skippedIds.current.size));
      } else {
        setCurrent(null);
        setPendingCount(resp.total);
      }
    } catch {
      setError("Failed to load review queue");
    } finally {
      setLoading(false);
    }
  }, [setPendingCount]);

  useEffect(() => {
    fetchNext();
  }, [fetchNext]);

  // Ref indirection breaks circular dependency: useCardDrag needs onCommit,
  // but handleCommit needs drag.flyOff. The ref lets useCardDrag call through
  // to the latest handleCommit without being in its dependency array.
  const handleCommitRef = useRef<(action: Exclude<Selection, null>) => void>(() => {});
  const drag = useCardDrag(cardRef, (action) => handleCommitRef.current(action), submitting);

  const handleCommit = useCallback(
    async (action: Exclude<Selection, null>) => {
      if (!current || submitting) return;
      setSubmitting(true);
      if (action === "skip") {
        skippedIds.current.add(current.knowledge_unit.id);
        await drag.flyOff(action);
        await fetchNext();
        setSubmitting(false);
        return;
      }
      setError(null);
      try {
        if (action === "approve") {
          await api.approve(current.knowledge_unit.id);
          setSessionApproved((n) => n + 1);
        } else {
          await api.reject(current.knowledge_unit.id);
          setSessionRejected((n) => n + 1);
        }
        await drag.flyOff(action);
        await fetchNext();
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          setConflictMessage("Already reviewed");
          setTimeout(() => fetchNext(), 1500);
        } else {
          setError("Something went wrong \u2014 try again");
        }
      } finally {
        setSubmitting(false);
      }
    },
    [current, submitting, fetchNext, drag],
  );
  handleCommitRef.current = handleCommit;

  const confirmAction = useCallback(() => {
    if (!selection) return;
    handleCommit(selection);
  }, [selection, handleCommit]);

  const handleSelect = useCallback((s: Selection) => {
    setSelection(s);
  }, []);

  // Keyboard handler.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.repeat || !current || loading || submitting) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setSelection("reject");
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setSelection("approve");
      } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        setSelection("skip");
      } else if ((e.key === " " || e.key === "Enter") && selection) {
        e.preventDefault();
        confirmAction();
      } else if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        handleCommit("skip");
      } else if (e.key === "Escape") {
        setSelection(null);
        drag.snapBack();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [current, loading, submitting, selection, confirmAction, handleCommit, drag]);

  if (loading) {
    return (
      <div className="flex justify-center mt-16">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (!current) {
    const total = sessionApproved + sessionRejected;
    const hasSkipped = skippedIds.current.size > 0;
    return (
      <div className="max-w-xl mx-auto border-2 border-gray-200 rounded-lg bg-white p-10 text-center mt-8">
        <div className="text-4xl mb-3">{hasSkipped ? "\u23ed" : "\u2713"}</div>
        <h2 className="text-lg font-semibold text-gray-900 mb-1">
          {hasSkipped ? "All remaining skipped" : "All caught up"}
        </h2>
        {hasSkipped && (
          <p className="text-gray-500">
            {skippedIds.current.size} skipped {skippedIds.current.size === 1 ? "item" : "items"} still pending
          </p>
        )}
        {total > 0 && (
          <>
            <p className="text-gray-500">You've reviewed {total} KUs today</p>
            <div className="flex gap-4 justify-center mt-3 text-sm">
              <span className="text-red-600 font-medium">{sessionRejected} rejected</span>
              <span className="text-gray-300">{"\u00b7"}</span>
              <span className="text-green-600 font-medium">{sessionApproved} approved</span>
            </div>
          </>
        )}
        {hasSkipped && (
          <button
            onClick={() => { skippedIds.current.clear(); fetchNext(); }}
            className="inline-block mt-5 text-sm font-medium text-indigo-500 hover:text-indigo-700"
          >
            Review skipped items
          </button>
        )}
        <Link to="/dashboard" className="inline-block mt-5 text-sm font-medium text-indigo-500 ml-4">
          View dashboard {"\u2192"}
        </Link>
      </div>
    );
  }

  return (
    <div>
      {conflictMessage && (
        <p className="text-center text-amber-600 text-sm font-medium mb-3">
          {conflictMessage}
        </p>
      )}

      <DragIndicators drag={drag.drag} />

      <ReviewCard
        ref={cardRef}
        unit={current.knowledge_unit}
        selection={selection}
        drag={drag.drag}
        pointerHandlers={drag.handlers}
      />

      <ReviewActions
        selection={selection}
        onSelect={handleSelect}
        onConfirm={confirmAction}
        disabled={submitting}
      />

      {error && (
        <p className="text-center text-red-600 text-sm mt-3">{error}</p>
      )}
    </div>
  );
}
