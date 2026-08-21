import type { MetadataRoute } from "next";
import { admissionGuides } from "@/content/guides";
import { SITE_URL } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const stablePages = ["", "/chat", "/eligibility", "/programs", "/blog"];
  return [
    ...stablePages.map((path) => ({
      url: new URL(path || "/", SITE_URL).toString(),
      lastModified: new Date("2026-08-22"),
      changeFrequency: path === "" ? ("weekly" as const) : ("monthly" as const),
      priority: path === "" ? 1 : 0.8,
    })),
    ...admissionGuides.map((guide) => ({
      url: new URL(`/blog/${guide.slug}`, SITE_URL).toString(),
      lastModified: new Date(guide.updated),
      changeFrequency: "monthly" as const,
      priority: 0.7,
    })),
  ];
}
