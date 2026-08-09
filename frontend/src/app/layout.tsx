import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DIU Admission AI",
  description: "Research prototype for Daffodil International University admission assistance.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
