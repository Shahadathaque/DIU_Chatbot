import type { Metadata } from "next";

export const SITE_NAME = "DIU Admission AI";
export const SITE_DESCRIPTION =
  "AI-powered admission assistance grounded in verified Daffodil International University information.";
export const PROJECT_AUTHOR = "DIU Admission AI Project";

const DEFAULT_SITE_URL = "https://diu-chatbot-blond.vercel.app";

function resolveSiteUrl(value: string | undefined): URL {
  const candidate = value?.trim() || DEFAULT_SITE_URL;
  const url = new URL(candidate);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (url.pathname !== "/" && url.pathname !== "")
  ) {
    throw new Error("NEXT_PUBLIC_SITE_URL must be an exact public HTTPS origin");
  }
  return new URL(url.origin);
}

export const SITE_URL = resolveSiteUrl(process.env.NEXT_PUBLIC_SITE_URL);

interface PageMetadataInput {
  title: string;
  description: string;
  path: string;
  type?: "website" | "article";
  publishedTime?: string;
  modifiedTime?: string;
  keywords?: string[];
}

export function createPageMetadata({
  title,
  description,
  path,
  type = "website",
  publishedTime,
  modifiedTime,
  keywords,
}: PageMetadataInput): Metadata {
  const canonical = new URL(path, SITE_URL).toString();
  return {
    title,
    description,
    keywords,
    alternates: { canonical },
    authors: [{ name: PROJECT_AUTHOR }],
    creator: PROJECT_AUTHOR,
    openGraph: {
      type,
      url: canonical,
      siteName: SITE_NAME,
      title,
      description,
      images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: SITE_NAME }],
      ...(type === "article" ? { publishedTime, modifiedTime } : {}),
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: ["/opengraph-image"],
    },
  };
}

export function serializeJsonLd(value: object): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}
