import "./globals.css";

import type { Metadata } from "next";
import { Inter, Space_Grotesk, Space_Mono } from "next/font/google";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const grotesk = Space_Grotesk({
  subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-space-grotesk",
});
const mono = Space_Mono({
  subsets: ["latin"], weight: ["400", "700"], variable: "--font-space-mono",
});

export const metadata: Metadata = {
  title: "ATS Resumaker",
  description: "Grounded, ATS-optimized job discovery + application tracking.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${grotesk.variable} ${mono.variable}`}>
      <body>
        <div className="glow-bg" />
        {/* No app shell here — the sidebar/grid live in app/(app)/layout.tsx (gated pages).
            Public pages (landing, login, setup) render bare on top of the ambient glow. */}
        {children}
      </body>
    </html>
  );
}
