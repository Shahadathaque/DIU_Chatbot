import type { Metadata } from "next";
import { Geist, Geist_Mono, Noto_Sans_Bengali } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { ResearchNotice } from "@/components/layout/research-notice";
import { serializeJsonLd, SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const notoBengali = Noto_Sans_Bengali({
  variable: "--font-noto-bengali",
  subsets: ["bengali"],
});

export const metadata: Metadata = {
  metadataBase: SITE_URL,
  title: {
    default: SITE_NAME,
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  category: "education",
  authors: [{ name: "DIU Admission AI Project" }],
  creator: "DIU Admission AI Project",
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    url: "/",
    siteName: SITE_NAME,
    title: SITE_NAME,
    description: SITE_DESCRIPTION,
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: SITE_NAME }],
  },
  twitter: { card: "summary_large_image", title: SITE_NAME, description: SITE_DESCRIPTION, images: ["/opengraph-image"] },
  verification: {
    google: process.env.GOOGLE_SITE_VERIFICATION,
    other: process.env.BING_SITE_VERIFICATION ? { "msvalidate.01": process.env.BING_SITE_VERIFICATION } : undefined,
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${notoBengali.variable} h-full scroll-smooth antialiased`}
    >
      <body className="min-h-full bg-canvas text-ink">
        <script
          dangerouslySetInnerHTML={{
            __html: serializeJsonLd({
              "@context": "https://schema.org",
              "@graph": [
                { "@type": "WebSite", name: SITE_NAME, url: SITE_URL.toString(), description: SITE_DESCRIPTION },
                { "@type": "WebApplication", name: SITE_NAME, url: SITE_URL.toString(), applicationCategory: "EducationalApplication", operatingSystem: "Web", description: SITE_DESCRIPTION },
              ],
            }),
          }}
          type="application/ld+json"
        />
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <div className="flex min-h-screen flex-col">
          <Header />
          <ResearchNotice />
          <main id="main-content" className="flex-1">
            {children}
          </main>
          <Footer />
        </div>
        <Analytics />
      </body>
    </html>
  );
}
