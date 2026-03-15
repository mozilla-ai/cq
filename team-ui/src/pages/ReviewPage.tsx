import { useState, useEffect, useCallback } from "react";
import { Link, useOutletContext } from "react-router";
import { api, ApiError } from "../api";
import { ReviewCard } from "../components/ReviewCard";
import type { ReviewItem } from "../types";

type Selection = "approve" | "reject" | null;

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

  const fetchNext = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSelection(null);
    setConflictMessage(null);
    try {
      const resp = await api.reviewQueue(1, 0);
      setCurrent(resp.items[0] ?? null);
      setPendingCount(resp.total);
    } catch {
      setError("Failed to load review queue");
    } finally {
      setLoading(false);
    }
  }, [setPendingCount]);

  useEffect(() => {
    fetchNext();
  }, [fetchNext]);

  const confirmAction = useCallback(async () => {
    if (!current || !selection || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      if (selection === "approve") {
        await api.approve(current.knowledge_unit.id);
        setSessionApproved((n) => n + 1);
      } else {
        await api.reject(current.knowledge_unit.id);
        setSessionRejected((n) => n + 1);
      }
      await fetchNext();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflictMessage("Already reviewed");
        setTimeout(() => fetchNext(), 1500);
      } else {
        setError("Something went wrong — try again");
      }
    } finally {
      setSubmitting(false);
    }
  }, [current, selection, submitting, fetchNext]);

  const handleSelect = useCallback(
    (s: Selection) => {
      setSelection(s);
    },
    [],
  );

  // Keyboard handler.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!current || loading || submitting) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setSelection("reject");
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setSelection("approve");
      } else if (e.key === " " && selection) {
        e.preventDefault();
        confirmAction();
      } else if (e.key === "Escape") {
        setSelection(null);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [current, loading, submitting, selection, confirmAction]);

  if (loading) {
    return (
      <div className="flex justify-center mt-16">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (!current) {
    const total = sessionApproved + sessionRejected;
    return (
      <div className="max-w-xl mx-auto border-2 border-gray-200 rounded-lg bg-white p-10 text-center mt-8">
        <div className="text-4xl mb-3">✓</div>
        <h2 className="text-lg font-semibold text-gray-900 mb-1">All caught up</h2>
        {total > 0 && (
          <>
            <p className="text-gray-500">You've reviewed {total} KUs today</p>
            <div className="flex gap-4 justify-center mt-3 text-sm">
              <span className="text-red-600 font-medium">{sessionRejected} rejected</span>
              <span className="text-gray-300">·</span>
              <span className="text-green-600 font-medium">{sessionApproved} approved</span>
            </div>
          </>
        )}
        <Link to="/dashboard" className="inline-block mt-5 text-sm font-medium text-indigo-500">
          View dashboard →
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

      <ReviewCard
        unit={current.knowledge_unit}
        selection={selection}
        onSelect={handleSelect}
      />

      {error && (
        <p className="text-center text-red-600 text-sm mt-3">{error}</p>
      )}
    </div>
  );
}
