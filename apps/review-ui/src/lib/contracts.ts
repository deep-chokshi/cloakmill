export type Project = {
  id: string;
  name: string;
  sourceCount: number;
  createdAt: string;
};
export type Source = {
  id: string;
  name: string;
  format: string;
  records: number | null;
  coverage: "sample" | "unavailable";
  description: string;
  surfaces: string[];
  limitations: string[];
};
export type ActionResult = { error?: string };

export const stages = [
  { id: "overview", label: "Overview", glyph: "◫" },
  { id: "sources", label: "Sources", glyph: "▤" },
  { id: "discovery", label: "Discovery", glyph: "⌕" },
  { id: "identities", label: "Identity review", glyph: "♧" },
  { id: "profiles", label: "Replacement profiles", glyph: "⇄" },
  { id: "preview", label: "Preview", glyph: "◩" },
  { id: "validation", label: "Validation", glyph: "✓" },
  { id: "releases", label: "Releases", glyph: "↗" },
] as const;
