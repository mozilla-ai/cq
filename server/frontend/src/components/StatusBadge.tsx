const STYLES: Record<string, string> = {
  proposed:
    "bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300",
  approved:
    "bg-green-100 dark:bg-green-500/20 text-green-800 dark:text-green-300",
  rejected: "bg-red-100 dark:bg-red-500/20 text-red-800 dark:text-red-300",
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status] ?? "bg-gray-100 dark:bg-slate-700 text-gray-800 dark:text-slate-300"}`}
    >
      {status}
    </span>
  )
}
