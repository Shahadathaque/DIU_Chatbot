export const suggestedQuestions = [
  "What documents are required for bachelor admission?",
  "Can I select the diploma pathway in the online application?",
  "Which scholarship categories does DIU list?",
  "What steps does DIU's admission flowchart show?",
  "Show DIU's official program catalog",
  "What documents are required for an online application?",
];

export function SuggestedQuestions({
  onSelect,
  disabled,
}: {
  onSelect: (question: string) => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <p className="mb-3 text-xs font-bold uppercase tracking-[0.11em] text-muted">
        Popular questions
      </p>
      <div className="flex flex-wrap gap-2">
        {suggestedQuestions.map((question) => (
          <button
            className="rounded-full border border-line bg-white px-3.5 py-2 text-left text-xs font-semibold text-ink transition hover:border-emerald-300 hover:bg-brand-soft disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled}
            key={question}
            onClick={() => onSelect(question)}
            type="button"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
