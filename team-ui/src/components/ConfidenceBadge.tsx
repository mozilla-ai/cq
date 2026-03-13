export function ConfidenceBadge({ confidence }: { confidence: number }) {
  return (
    <span className="text-sm text-gray-500">
      Confidence: <strong className="text-gray-800">{confidence.toFixed(2)}</strong>
    </span>
  );
}
