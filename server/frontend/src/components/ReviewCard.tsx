import { forwardRef } from "react"
import type { DragState, PointerHandlers } from "../hooks/useCardDrag"
import {
  FLY_OFF_MS,
  MAX_ROTATION_DEG,
  SNAP_BACK_MS,
} from "../hooks/useCardDrag"
import type { KnowledgeUnit, Selection } from "../types"
import { timeAgo } from "../utils"
import { DomainTags } from "./DomainTags"

interface Props {
  unit: KnowledgeUnit
  selection: Selection
  drag: DragState
  pointerHandlers: PointerHandlers
}

const CARD_STYLES: Record<string, string> = {
  neutral: "border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900",
  approve:
    "border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-950/40",
  reject: "border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40",
  skip: "border-slate-400 dark:border-slate-600 bg-slate-50 dark:bg-slate-800",
}

const ACTION_BOX_STYLES: Record<string, string> = {
  neutral:
    "bg-indigo-50 dark:bg-indigo-950/40 border-indigo-500 text-indigo-500",
  approve:
    "bg-green-50 dark:bg-green-950/40 border-green-500 text-green-600 dark:text-green-400",
  reject:
    "bg-red-50 dark:bg-red-950/40 border-red-500 text-red-600 dark:text-red-400",
  skip: "bg-slate-50 dark:bg-slate-800 border-slate-400 text-slate-500 dark:text-slate-300",
}

function confidenceColor(c: number): string {
  if (c < 0.3) return "text-red-600 dark:text-red-400"
  if (c < 0.5) return "text-amber-600 dark:text-amber-400"
  if (c < 0.7) return "text-yellow-500 dark:text-yellow-400"
  return "text-green-600 dark:text-green-400"
}

export const ReviewCard = forwardRef<HTMLDivElement, Props>(function ReviewCard(
  { unit, selection, drag, pointerHandlers },
  ref,
) {
  const activeState =
    drag.isDragging || drag.isFlyingOff ? drag.dragAction : selection
  const cardStyle = CARD_STYLES[activeState ?? "neutral"]
  const actionBoxStyle = ACTION_BOX_STYLES[activeState ?? "neutral"]

  const rotation = drag.isDragging
    ? (drag.offset.x / 300) * MAX_ROTATION_DEG
    : 0
  const shadowScale = drag.isDragging ? 1 + drag.dragProgress * 0.5 : 1
  const transform = `translate(${drag.offset.x}px, ${drag.offset.y}px) rotate(${rotation}deg)`
  const transition = drag.isDragging
    ? "none"
    : drag.isFlyingOff
      ? `transform ${FLY_OFF_MS}ms ease-in, box-shadow ${FLY_OFF_MS}ms ease-in`
      : `transform ${SNAP_BACK_MS}ms ease-out, box-shadow ${SNAP_BACK_MS}ms ease-out`
  const shadow = `0 ${4 * shadowScale}px ${20 * shadowScale}px rgba(0,0,0,${0.08 * shadowScale})`

  return (
    <div
      ref={ref}
      className={`relative z-0 border-2 rounded-lg p-6 max-w-xl mx-auto select-none touch-none ${cardStyle}`}
      style={{ transform, transition, boxShadow: shadow }}
      {...pointerHandlers}
    >
      <div className="flex items-center justify-between mb-3">
        <DomainTags domains={unit.domains} variant={activeState} />
        {unit.evidence.first_observed && (
          <span className="text-xs text-gray-400 dark:text-slate-500">
            {timeAgo(unit.evidence.first_observed)}
          </span>
        )}
      </div>

      <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100 mb-2">
        {unit.insight.summary}
      </h2>

      <p className="text-gray-600 dark:text-slate-300 mb-3 leading-relaxed">
        {unit.insight.detail}
      </p>

      <div
        className={`border-l-3 rounded-r-lg px-4 py-3 mb-6 ${actionBoxStyle}`}
      >
        <span className="text-xs font-semibold uppercase tracking-wide">
          Action
        </span>
        <p className="text-gray-800 dark:text-slate-200 text-sm mt-1">
          {unit.insight.action}
        </p>
      </div>

      <div className="flex gap-4 text-sm text-gray-500 dark:text-slate-400">
        <span>
          Confidence:{" "}
          <strong className={confidenceColor(unit.evidence.confidence)}>
            {unit.evidence.confidence.toFixed(2)}
          </strong>
        </span>
        <span>
          Confirmations:{" "}
          <strong className="text-gray-800 dark:text-slate-200">
            {unit.evidence.confirmations}
          </strong>
        </span>
      </div>
    </div>
  )
})
