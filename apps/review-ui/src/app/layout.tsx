import type { ReactNode } from "react";
import type { Metadata } from "next";
import localFont from "next/font/local";
import { connection } from "next/server";
import { WorkspaceShell } from "@/components/workspace-shell";
import { readProjects, sampleMode } from "@/server/workspace";
import "./globals.css";

const plex = localFont({
  src: "../assets/IBMPlexSans-Variable.ttf",
  variable: "--font-sans",
  display: "swap",
});
const instrument = localFont({
  src: "../assets/InstrumentSerif-Regular.ttf",
  variable: "--font-display",
  display: "swap",
  weight: "400",
});
export const metadata: Metadata = {
  title: "CloakMill — Workspace",
  description: "CloakMill sample workspace. Fictional records only.",
  robots: { index: false, follow: false },
};

export default async function Layout({ children }: { children: ReactNode }) {
  await connection();
  const projects = await readProjects();
  return (
    <html lang="en" className={`${plex.variable} ${instrument.variable}`}>
      <body>
        <WorkspaceShell projects={projects} enabled={sampleMode()}>
          {children}
        </WorkspaceShell>
      </body>
    </html>
  );
}
