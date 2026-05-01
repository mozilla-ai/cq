import type { Selection } from "../types"

const TAG_STYLES: Record<string, string> = {
  neutral: "bg-indigo-100 text-indigo-700",
  approve: "bg-green-100 text-green-700",
  reject: "bg-red-100 text-red-700",
  skip: "bg-slate-100 text-slate-700",
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
