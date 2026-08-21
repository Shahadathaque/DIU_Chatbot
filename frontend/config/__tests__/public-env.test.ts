import { describe, expect, it } from "vitest";
import { resolvePublicFrontendConfig } from "../public-env";

describe("public frontend environment", () => {
  it("keeps self-contained mock defaults for local development", () => {
    expect(resolvePublicFrontendConfig({})).toEqual({
      apiUrl: "http://localhost:8000",
      useMockApi: "true",
    });
  });

  it("requires real API mode and an explicit URL on Vercel production", () => {
    expect(() =>
      resolvePublicFrontendConfig({ VERCEL_ENV: "production" }),
    ).toThrow(/NEXT_PUBLIC_API_URL/);
    expect(() =>
      resolvePublicFrontendConfig({
        VERCEL_ENV: "production",
        NEXT_PUBLIC_USE_MOCK_API: "true",
        NEXT_PUBLIC_API_URL: "https://api.example.com",
      }),
    ).toThrow(/MOCK_API=false/);
  });

  it.each([
    "http://api.example.com",
    "https://localhost:8000",
    "https://user:password@api.example.com",
    "https://api.example.com/v1",
  ])("rejects unsafe production API URL %s", (apiUrl) => {
    expect(() =>
      resolvePublicFrontendConfig({
        VERCEL_ENV: "production",
        NEXT_PUBLIC_USE_MOCK_API: "false",
        NEXT_PUBLIC_API_URL: apiUrl,
      }),
    ).toThrow(/public HTTPS origin/);
  });

  it("normalizes a valid production configuration", () => {
    expect(
      resolvePublicFrontendConfig({
        VERCEL_ENV: "production",
        NEXT_PUBLIC_USE_MOCK_API: "false",
        NEXT_PUBLIC_API_URL: "https://api.example.com/",
      }),
    ).toEqual({
      apiUrl: "https://api.example.com",
      useMockApi: "false",
    });
  });

  it("rejects typoed mock flags instead of silently enabling mock mode", () => {
    expect(() =>
      resolvePublicFrontendConfig({ NEXT_PUBLIC_USE_MOCK_API: "flase" }),
    ).toThrow(/true or false/);
  });
});
