import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Triage review console",
  description: "Review, edit and approve AI-drafted replies before they are sent.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
