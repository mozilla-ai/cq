import type { Selection } from "../types"

const TAG_STYLES: Record<string, string> = {
  neutral:
    "bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300",
  approve:
    "bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-300",
  reject: "bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300",
  skip: "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300",
}

interface Props {
  domains: string[]
  variant?: Selection
}

export function DomainTags({ domains, variant }: Props) {
  const style = TAG_STYLES[variant ?? "neutral"]
  return (
    <div className="flex flex-wrap gap-1.5">
      {[...domains].sort().map((d) => (
        <span
          key={d}
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}
        >
          {d}
        </span>
      ))}
    </div>
  )
}
