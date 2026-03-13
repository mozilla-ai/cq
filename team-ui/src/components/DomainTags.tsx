export function DomainTags({ domains }: { domains: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {domains.map((d) => (
        <span
          key={d}
          className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-700"
        >
          {d}
        </span>
      ))}
    </div>
  );
}
