export interface PublicFrontendConfig {
  apiUrl: string;
  useMockApi: "true" | "false";
}

/** Resolve browser-visible settings and fail closed for Vercel production. */
export function resolvePublicFrontendConfig(
  env: Record<string, string | undefined>,
): PublicFrontendConfig {
  const productionDeployment = env.VERCEL_ENV?.trim() === "production";
  const rawMock = env.NEXT_PUBLIC_USE_MOCK_API?.trim().toLowerCase();
  if (rawMock && rawMock !== "true" && rawMock !== "false") {
    throw new Error("NEXT_PUBLIC_USE_MOCK_API must be either true or false");
  }
  const useMock = rawMock ? rawMock === "true" : !productionDeployment;
  const apiUrl = (
    env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:8000"
  ).replace(/\/+$/, "");

  if (productionDeployment) {
    if (useMock) {
      throw new Error(
        "Vercel production requires NEXT_PUBLIC_USE_MOCK_API=false",
      );
    }
    if (!env.NEXT_PUBLIC_API_URL?.trim()) {
      throw new Error("Vercel production requires NEXT_PUBLIC_API_URL");
    }
    let parsed: URL;
    try {
      parsed = new URL(apiUrl);
    } catch {
      throw new Error("NEXT_PUBLIC_API_URL must be a valid HTTPS origin");
    }
    if (
      parsed.protocol !== "https:" ||
      !parsed.hostname ||
      parsed.username ||
      parsed.password ||
      (parsed.pathname !== "/" && parsed.pathname !== "") ||
      parsed.search ||
      parsed.hash ||
      parsed.hostname === "localhost" ||
      parsed.hostname === "127.0.0.1"
    ) {
      throw new Error(
        "Vercel production NEXT_PUBLIC_API_URL must be an exact public HTTPS origin",
      );
    }
  }
  return { apiUrl, useMockApi: useMock ? "true" : "false" };
}
