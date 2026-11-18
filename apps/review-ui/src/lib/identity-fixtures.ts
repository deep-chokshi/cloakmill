/**
 * Authored, fictional identity-review fixtures for the sample workspace.
 * Shapes mirror planned domain contracts (entity graph, review exceptions,
 * namespace-scoped synthetic profiles, frozen mapping snapshot refs).
 * No engine output, mapping vault material, or private locators are included.
 */

export type EntityKind = "person" | "shared_account" | "organization";

export type SampleEntity = {
  id: string;
  name: string;
  kind: EntityKind;
  role: string;
  initials: string;
  aliases: string[];
  sourceIds: string[];
};

export type ReviewChoice = {
  value: string;
  label: string;
  detail: string;
  recommended?: boolean;
};

export type ReviewCase = {
  id: string;
  title: string;
  kind: string;
  summary: string;
  explanation: string;
  evidenceLabel: string;
  evidenceText: string;
  choices: ReviewChoice[];
};

export type ProfileReplacement = {
  name: string;
  email: string;
};

export type ProfilePreset = {
  id: string;
  label: string;
  replacements: Record<string, ProfileReplacement>;
};

export const sampleEntities: SampleEntity[] = [
  {
    id: "p017",
    name: "Maya Shah",
    kind: "person",
    role: "Customer success",
    initials: "MS",
    aliases: ["Maya Shah", "M. Shah", "Maya"],
    sourceIds: ["directory", "messages", "handoff"],
  },
  {
    id: "p042",
    name: "Maya Chen",
    kind: "person",
    role: "Product marketing",
    initials: "MC",
    aliases: ["Maya Chen", "Maya"],
    sourceIds: ["directory", "messages"],
  },
  {
    id: "p009",
    name: "Daniel Kim",
    kind: "person",
    role: "Account operations",
    initials: "DK",
    aliases: ["Daniel Kim", "Daniel"],
    sourceIds: ["directory", "messages", "handoff"],
  },
  {
    id: "p023",
    name: "Priya Rao",
    kind: "person",
    role: "Finance operations",
    initials: "PR",
    aliases: ["Priya Rao", "Priya"],
    sourceIds: ["directory", "messages", "handoff"],
  },
  {
    id: "a003",
    name: "Finance mailbox",
    kind: "shared_account",
    role: "Team-owned mailbox",
    initials: "FA",
    aliases: ["finance@acme.example"],
    sourceIds: ["directory", "messages"],
  },
  {
    id: "o001",
    name: "Acme",
    kind: "organization",
    role: "Source organization",
    initials: "AC",
    aliases: ["Acme"],
    sourceIds: ["messages", "handoff"],
  },
];

export const sampleReviewCases: ReviewCase[] = [
  {
    id: "maya",
    title: "Which Maya is this?",
    kind: "Ambiguous first name",
    summary: "One short name, two distinct people.",
    explanation:
      "Two people share this first name. The invoice thread includes Maya Shah; Maya Chen belongs to a separate marketing conversation.",
    evidenceLabel:
      "Operations conversations.json · Message 2 (authored sample)",
    evidenceText:
      "From: Priya Rao\nThread participants: Priya Rao, Maya Shah\n\nMaya will send the revised invoice for AC-104.\nThe review deadline is 2026-02-03.",
    choices: [
      {
        value: "p017",
        label: "Maya Shah",
        detail: "Customer success · present in this thread",
        recommended: true,
      },
      {
        value: "p042",
        label: "Maya Chen",
        detail: "Product marketing · a different conversation",
      },
    ],
  },
  {
    id: "finance",
    title: "A mailbox, not a person",
    kind: "Shared-account boundary",
    summary: "A forwarded signature can create a false link.",
    explanation:
      "The finance address appears above Maya's forwarded signature. The directory identifies it as a shared account; it should retain a separate identity.",
    evidenceLabel:
      "Operations conversations.json · Message 3 (authored sample)",
    evidenceText:
      "From: finance@acme.example\nAccount type in directory: shared\n\nPayment received for AC-104.\n\nForwarded signature:\nMaya Shah | Customer success",
    choices: [
      {
        value: "shared",
        label: "Keep as a shared account",
        detail: "Preserve the team mailbox separately from Maya",
        recommended: true,
      },
    ],
  },
];

export const sampleProfilePresets: ProfilePreset[] = [
  {
    id: "birch",
    label: "Birch / sample profile A",
    replacements: {
      p017: { name: "Nora Reed", email: "nora.reed@birch.example" },
      p042: { name: "Iris Cole", email: "iris.cole@birch.example" },
      p009: { name: "Evan Park", email: "evan.park@birch.example" },
      p023: { name: "Lena Shaw", email: "lena.shaw@birch.example" },
      a003: { name: "Accounts mailbox", email: "accounts@birch.example" },
      o001: { name: "Birch", email: "" },
    },
  },
  {
    id: "cedar",
    label: "Cedar / sample profile B",
    replacements: {
      p017: { name: "Julia West", email: "julia.west@cedar.example" },
      p042: { name: "Thea Gray", email: "thea.gray@cedar.example" },
      p009: { name: "Owen Bell", email: "owen.bell@cedar.example" },
      p023: { name: "Mira Lane", email: "mira.lane@cedar.example" },
      a003: { name: "Accounts mailbox", email: "accounts@cedar.example" },
      o001: { name: "Cedar", email: "" },
    },
  },
];

export function namespaceForProject(name: string): string {
  const slug =
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "research-pilot";
  return `sample-ns / ${slug} / research`;
}
