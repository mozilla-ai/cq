export function ConfidenceBadge({ confidence }: { confidence: number }) {
  return (
    <span className="text-sm text-gray-500 dark:text-slate-400">
      Confidence:{" "}
      <strong className="text-gray-800 dark:text-slate-200">
        {confidence.toFixed(2)}
      </strong>
    </span>
  )
}
