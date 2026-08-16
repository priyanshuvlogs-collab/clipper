import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Clapperboard } from "lucide-react";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Pro Clipper — AI Video Clipping Studio",
  description:
    "Turn long videos into viral Shorts, Reels and TikToks. AI transcription (Hindi + English), smart moment detection, vertical rendering with burned-in captions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased`}>
        <header className="sticky top-0 z-40 border-b border-border/70 bg-background/70 backdrop-blur-xl">
          <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent shadow-lg shadow-primary/30">
                <Clapperboard className="h-4.5 w-4.5 text-white" strokeWidth={2.2} />
              </span>
              <span className="text-[15px] font-bold tracking-tight">
                Pro Clipper
                <span className="ml-2 rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
                  AI Studio
                </span>
              </span>
            </Link>
            <nav className="flex items-center gap-4 text-sm text-muted">
              <Link href="/" className="transition hover:text-foreground">
                Dashboard
              </Link>
              <a
                href="/api/health"
                target="_blank"
                rel="noreferrer"
                className="transition hover:text-foreground"
              >
                API
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
