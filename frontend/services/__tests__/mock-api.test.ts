import { describe, expect, it } from "vitest";
import {
  mockCheckEligibility,
  mockGetPrograms,
  mockSendChatMessage,
} from "../mock-api";

describe("mock API fixtures", () => {
  it("returns a non-empty chat answer for each language", async () => {
    for (const language of ["en", "bn", "banglish"] as const) {
      const response = await mockSendChatMessage({
        message: "What documents do I need?",
        language,
      });
      expect(response.answer.trim().length).toBeGreaterThan(0);
      expect(response.sources?.length).toBeGreaterThan(0);
    }
  });

  it("never invents an eligibility decision locally", async () => {
    const response = await mockCheckEligibility({
      program: "CSE",
      ssc_gpa: 5,
      hsc_gpa: 5,
      group: "Science",
    });

    expect(["eligible", "not_eligible", "insufficient_information"]).toContain(
      response.status,
    );
    expect(response.reason.trim().length).toBeGreaterThan(0);
  });

  it("returns a program list array", async () => {
    const response = await mockGetPrograms();
    expect(Array.isArray(response.programs)).toBe(true);
    expect(response.programs.length).toBeGreaterThan(0);
    expect(response.programs[0]).toHaveProperty("id");
    expect(response.programs[0]).toHaveProperty("name");
  });
});
