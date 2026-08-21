import { describe, expect, it } from "vitest";
import { admissionGuides, getGuide } from "@/content/guides";

const allowedHosts = new Set([
  "daffodilvarsity.edu.bd",
  "webbackend.daffodilvarsity.edu.bd",
  "financialaid.daffodilvarsity.edu.bd",
  "pd.daffodilvarsity.edu.bd",
]);

describe("admission guide catalog", () => {
  it("contains a compact set of substantial, uniquely addressed guides", () => {
    expect(admissionGuides.length).toBeGreaterThanOrEqual(5);
    expect(admissionGuides.length).toBeLessThanOrEqual(8);
    expect(new Set(admissionGuides.map(({ slug }) => slug)).size).toBe(admissionGuides.length);
    expect(new Set(admissionGuides.map(({ title }) => title)).size).toBe(admissionGuides.length);
    for (const guide of admissionGuides) {
      expect(guide.sections.length).toBeGreaterThanOrEqual(3);
      expect(guide.sources.length).toBeGreaterThan(0);
      expect(Number.isNaN(Date.parse(guide.published))).toBe(false);
      expect(Number.isNaN(Date.parse(guide.updated))).toBe(false);
      expect(getGuide(guide.slug)).toBe(guide);
    }
  });

  it("uses only approved official-source hosts and valid related links", () => {
    const slugs = new Set(admissionGuides.map(({ slug }) => slug));
    for (const guide of admissionGuides) {
      for (const source of guide.sources) {
        const url = new URL(source.url);
        expect(url.protocol).toBe("https:");
        expect(allowedHosts.has(url.hostname)).toBe(true);
      }
      for (const relatedSlug of guide.relatedSlugs) expect(slugs.has(relatedSlug)).toBe(true);
    }
  });
});
