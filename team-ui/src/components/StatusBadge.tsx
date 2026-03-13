const STYLES: Record<string, string> = {
  proposed: "bg-amber-100 text-amber-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status] ?? "bg-gray-100 text-gray-800"}`}
    >
      {status}
    </span>
  );
}
