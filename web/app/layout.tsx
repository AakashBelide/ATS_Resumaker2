import "./globals.css";

import type { Metadata } from "next";
import { Inter, Space_Grotesk, Space_Mono } from "next/font/google";

import Sidebar from "@/components/Sidebar";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const grotesk = Space_Grotesk({
  subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-space-grotesk",
});
const mono = Space_Mono({
  subsets: ["latin"], weight: ["400", "700"], variable: "--font-space-mono",
});

export const metadata: Metadata = {
  title: "resumaker",
  description: "Grounded, ATS-optimized job discovery + application tracking.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${grotesk.variable} ${mono.variable}`}>
      <body>
        <div className="glow-bg" />
        <div className="app">
          <Sidebar />
          <div className="content">{children}</div>
        </div>
      </body>
    </html>
  );
}
