import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Mono, Manrope } from "next/font/google";
import { Providers } from "@/components/providers";
import { themeBootScript } from "@/lib/theme";
import "./globals.css";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
});

const atkinsonMono = Atkinson_Hyperlegible_Mono({
  variable: "--font-atkinson-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "QuoteLens",
  description: "Turn a bill of materials into a quote you can defend, line by line.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Font variables sit on <html>: Tailwind resolves --font-sans on :root, so variables set
  // lower (on <body>) leave it invalid. The boot script sets data-theme on <html> before
  // paint, hence suppressHydrationWarning.
  return (
    <html lang="en" className={`${manrope.variable} ${atkinsonMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript() }} />
      </head>
      <body className="antialiased">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
