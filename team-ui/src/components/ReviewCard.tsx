import { forwardRef } from "react";
import type { KnowledgeUnit, Selection } from "../types";
import { DomainTags } from "./DomainTags";
import { timeAgo } from "../utils";
import type { DragState, GestureHandlers } from "../hooks/useCardDrag";
import { FLY_OFF_MS, MAX_ROTATION_DEG, SNAP_BACK_MS } from "../hooks/useCardDrag";

interface Props {
  unit: KnowledgeUnit;
  selection: Selection;
  drag: DragState;
  pointerHandlers: GestureHandlers;
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

export const ReviewCard = forwardRef<HTMLDivElement, Props>(
  function ReviewCard({ unit, selection, drag, pointerHandlers }, ref) {
    const activeState = drag.isDragging || drag.isFlyingOff ? drag.dragAction : selection;
    const cardStyle = CARD_STYLES[activeState ?? "neutral"];
    const actionBoxStyle = ACTION_BOX_STYLES[activeState ?? "neutral"];

    const rotation = drag.isDragging
      ? (drag.offset.x / 300) * MAX_ROTATION_DEG
      : 0;
    const shadowScale = drag.isDragging ? 1 + drag.dragProgress * 0.5 : 1;
    const transform = `translate(${drag.offset.x}px, ${drag.offset.y}px) rotate(${rotation}deg)`;
    const transition = drag.isDragging
      ? "none"
      : drag.isFlyingOff
        ? `transform ${FLY_OFF_MS}ms ease-in, box-shadow ${FLY_OFF_MS}ms ease-in`
        : `transform ${SNAP_BACK_MS}ms ease-out, box-shadow ${SNAP_BACK_MS}ms ease-out`;
    const shadow = `0 ${4 * shadowScale}px ${20 * shadowScale}px rgba(0,0,0,${0.08 * shadowScale})`;

    return (
      <div
        ref={ref}
        className={`relative z-0 mx-auto flex h-full max-h-full w-full max-w-xl select-none flex-col overflow-hidden rounded-lg border-2 p-4 touch-pan-y sm:p-6 ${cardStyle}`}
        style={{ transform, transition, boxShadow: shadow }}
        {...pointerHandlers}
      >
        <div className="mb-3 flex items-center justify-between">
          <DomainTags domains={unit.domain} variant={activeState} />
          <span className="text-xs text-gray-400">
            {timeAgo(unit.evidence.first_observed)}
          </span>
        </div>

        <h2 className="mb-3 text-lg font-semibold text-gray-900">
          {unit.insight.summary}
        </h2>

        <div
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1"
          data-scroll-region="true"
        >
          <p className="mb-3 leading-relaxed text-gray-600">
            {unit.insight.detail}
          </p>

          <div className={`mb-6 rounded-r-lg border-l-3 px-4 py-3 ${actionBoxStyle}`}>
            <span className="text-xs font-semibold uppercase tracking-wide">
              Action
            </span>
            <p className="mt-1 text-sm text-gray-800">{unit.insight.action}</p>
          </div>
        </div>

        <div className="flex gap-4 pt-3 text-sm text-gray-500">
          <span>
            Confidence: <strong className={confidenceColor(unit.evidence.confidence)}>{unit.evidence.confidence.toFixed(2)}</strong>
          </span>
          <span>
            Confirmations: <strong className="text-gray-800">{unit.evidence.confirmations}</strong>
          </span>
        </div>
      </div>
    );
  },
);
