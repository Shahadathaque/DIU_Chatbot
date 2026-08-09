import { SparkleIcon } from "@/components/ui/icons";

export function TypingIndicator() {
  return (
    <div className="flex items-end gap-3" aria-label="Assistant is preparing an answer" role="status">
      <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-brand text-white">
        <SparkleIcon size={15} />
      </span>
      <div className="flex h-11 items-center gap-1.5 rounded-2xl rounded-bl-md border border-line bg-white px-4 shadow-sm">
        {[0, 1, 2].map((item) => (
          <span
            className="size-1.5 animate-bounce rounded-full bg-brand"
            key={item}
            style={{ animationDelay: `${item * 130}ms` }}
          />
        ))}
      </div>
    </div>
  );
}
