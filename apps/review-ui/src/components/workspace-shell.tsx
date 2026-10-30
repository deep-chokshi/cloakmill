"use client";

import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";
import { stages, type Project } from "@/lib/contracts";
import { CreateProject } from "./project-form";

export function WorkspaceShell({
  projects,
  enabled,
  children,
}: {
  projects: Project[];
  enabled: boolean;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const currentId = pathname.split("/")[2];
  const project = projects.find((item) => item.id === currentId);
  const main = useRef<HTMLElement>(null);
  const drawer = useRef<HTMLDialogElement>(null);
  const menu = useRef<HTMLButtonElement>(null);
  const previous = useRef(pathname);
  useEffect(() => {
    if (previous.current !== pathname) {
      drawer.current?.close();
      main.current?.querySelector<HTMLElement>("h1")?.focus();
      previous.current = pathname;
    }
  }, [pathname]);
  function navigation() {
    return (
      <>
        <Link
          href="/"
          prefetch={false}
          className="brand"
          onClick={() => drawer.current?.close()}
        >
          <span className="brand-mark" aria-hidden="true">
            C<span>m</span>
          </span>
          <span>
            CloakMill<small>CONTEXT, PRESERVED.</small>
          </span>
        </Link>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <Link
          href="/"
          prefetch={false}
          className={`workspace-home ${!project ? "selected" : ""}`}
        >
          Projects <span aria-hidden="true">↗</span>
        </Link>
        {project && (
          <>
            <div className="current-project">
              <span className="project-monogram">
                {project.name.slice(0, 1).toUpperCase()}
              </span>
              <span>
                {project.name}
                <small>Fictional sample project</small>
              </span>
            </div>
            <nav aria-label="Project workflow">
              {stages.map((stage) => (
                <Link
                  key={stage.id}
                  prefetch={false}
                  href={`/projects/${project.id}/${stage.id}` as Route}
                  className={`nav-link ${pathname.includes(`/${stage.id}`) ? "active" : ""}`}
                  aria-current={
                    pathname.includes(`/${stage.id}`) ? "page" : undefined
                  }
                  onClick={() => drawer.current?.close()}
                >
                  <span aria-hidden="true">{stage.glyph}</span>
                  {stage.label}
                </Link>
              ))}
            </nav>
          </>
        )}
        <div className="sidebar-foot">
          <span className="live-dot" />{" "}
          {enabled ? "Sample environment" : "Backend not connected"}
          <p>Local assets. Fictional records.</p>
        </div>
      </>
    );
  }
  return (
    <div className="workspace-shell">
      <a href="#workspace-content" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar">{navigation()}</aside>
      <dialog
        className="nav-dialog"
        ref={drawer}
        aria-label="Workspace navigation"
        onClose={() => menu.current?.focus()}
      >
        <button
          className="nav-close"
          onClick={() => drawer.current?.close()}
          aria-label="Close navigation"
        >
          ×
        </button>
        {navigation()}
      </dialog>
      <div className="workspace-main">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              ref={menu}
              className="menu-button"
              aria-label="Open navigation"
              onClick={() => drawer.current?.showModal()}
            >
              ☰
            </button>
            <Link href="/" prefetch={false}>
              Workspace
            </Link>
            <span aria-hidden="true">/</span>
            <span>{project?.name ?? "Projects"}</span>
          </div>
          <div className="topbar-actions">
            <span className="environment-label">
              {enabled ? "SAMPLE MODE" : "NOT CONNECTED"}
            </span>
            {enabled && <CreateProject />}
          </div>
        </header>
        <main ref={main} id="workspace-content" tabIndex={-1}>
          {children}
        </main>
        <footer className="workspace-footer">
          <span>Fictional records only. No private files are read.</span>
          <span>Sample workspace · Fictional data</span>
        </footer>
        <div className="sr-only" role="status" aria-live="polite" />
      </div>
    </div>
  );
}
