import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Personal AI Workspace",
  description: "A personal workspace for files, useful analysis and learning.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="header">
          <Link href="/" className="brand">
            <span className="mark">P</span> PAW
          </Link>
          <nav aria-label="Main navigation">
            <Link href="/workspace">Workspace</Link>
          </nav>
          <span className="stage">Foundation · M0</span>
        </header>
        <main>{children}</main>
        <footer>
          Personal AI Workspace{" "}
          <span>Built one useful workflow at a time.</span>
        </footer>
      </body>
    </html>
  );
}
