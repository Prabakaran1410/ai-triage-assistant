import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

// Self-hosted by next/font at build time: no request to Google at runtime,
// and no layout shift from a late-loading webfont.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Triage review console",
  description: "Review, edit and approve AI-drafted replies before they are sent.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
