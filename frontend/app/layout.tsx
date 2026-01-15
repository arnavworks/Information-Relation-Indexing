import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Information Relation Index",
  description: "Source-resolved evidence routing and relational information retrieval.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
