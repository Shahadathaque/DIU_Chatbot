import { describe, expect, it } from "vitest";

import { suggestedQuestions } from "../../components/chat/suggested-questions";

describe("suggested questions", () => {
  it("uses only evidence-backed prompts tied to collected official sources", () => {
    expect(suggestedQuestions).toEqual([
      "What documents are required for bachelor admission?",
      "Can I select the diploma pathway in the online application?",
      "Which scholarship categories does DIU list?",
      "What steps does DIU's admission flowchart show?",
      "Show DIU's official program catalog",
      "What documents are required for an online application?",
    ]);
  });
});
