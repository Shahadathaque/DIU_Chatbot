import { describe, expect, it } from "vitest";
import { createPageMetadata, serializeJsonLd, SITE_URL } from "@/lib/site";

describe("site metadata helpers", () => {
  it("creates absolute canonical metadata", () => {
    const metadata = createPageMetadata({ title: "Programs", description: "Program directory", path: "/programs" });
    expect(metadata.alternates?.canonical).toBe(new URL("/programs", SITE_URL).toString());
    expect(metadata.openGraph).toMatchObject({ type: "website", title: "Programs" });
  });

  it("escapes markup-significant characters in JSON-LD", () => {
    expect(serializeJsonLd({ value: "</script>" })).not.toContain("</script>");
    expect(JSON.parse(serializeJsonLd({ value: "</script>" }))).toEqual({ value: "</script>" });
  });
});
