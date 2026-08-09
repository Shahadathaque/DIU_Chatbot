import type { Metadata } from "next";
import { Geist, Geist_Mono, Noto_Sans_Bengali } from "next/font/google";
import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { ResearchNotice } from "@/components/layout/research-notice";
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
  title: {
    default: "DIU Admission AI",
    template: "%s | DIU Admission AI",
  },
  description:
    "AI-powered admission assistance for Daffodil International University.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${notoBengali.variable} h-full scroll-smooth antialiased`}
    >
      <body className="min-h-full bg-canvas text-ink">
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
      </body>
    </html>
  );
}
