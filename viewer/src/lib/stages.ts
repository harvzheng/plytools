// Single source of truth for stages. Each canonical stage maps to a bucket
// (the badge color). Multiple stages can share a bucket — the label keeps the
// specificity, the bucket keeps the visual consistent.

export type Bucket =
  | "Folder only"
  | "Discovered"
  | "In progress"
  | "Drafts ready"
  | "Applied"
  | "Sent"
  | "Replied"
  | "Rejected";

export interface StageSpec {
  label: string;
  bucket: Bucket;
}

export const STAGES: StageSpec[] = [
  { label: "Discovered", bucket: "Discovered" },
  { label: "In progress", bucket: "In progress" },
  { label: "Drafts ready", bucket: "Drafts ready" },
  { label: "Applied", bucket: "Applied" },
  { label: "Sent", bucket: "Sent" },
  { label: "Warm-intro requested", bucket: "Sent" },
  { label: "Warm-referral requested", bucket: "Sent" },
  { label: "Recruiter screen scheduled", bucket: "Replied" },
  { label: "Recruiter screen passed", bucket: "Replied" },
  { label: "HM prelim scheduled", bucket: "Replied" },
  { label: "HM prelim completed", bucket: "Replied" },
  { label: "Team round scheduled", bucket: "Replied" },
  { label: "Team round passed", bucket: "Replied" },
  { label: "Final loop", bucket: "Replied" },
  { label: "Offer", bucket: "Replied" },
  { label: "On hold", bucket: "In progress" },
  { label: "Rejected", bucket: "Rejected" },
  { label: "Closed", bucket: "Rejected" },
];

// Display order for bucket groupings in the dropdown.
export const BUCKET_ORDER: Bucket[] = [
  "Discovered",
  "In progress",
  "Drafts ready",
  "Applied",
  "Sent",
  "Replied",
  "Rejected",
  "Folder only",
];

const LABEL_TO_BUCKET: Record<string, Bucket> = Object.fromEntries(
  STAGES.map((s) => [s.label.toLowerCase(), s.bucket])
);

// Resolve any stage string (canonical label or free-text legacy value) to a
// bucket. Exact label matches first; otherwise fall back to the fuzzy regex
// catalog so older entries like "Contacts tiered; awaiting target selection"
// still bucket correctly.
export function bucketOf(raw: string): Bucket {
  const key = raw.trim().toLowerCase();
  const hit = LABEL_TO_BUCKET[key];
  if (hit) return hit;
  if (key === "folder only") return "Folder only";
  if (/(reject|\bno\b|did not move forward|not moving forward|closed)/.test(key)) return "Rejected";
  if (/(reply|replied|interview|offer|screen passed|passed)/.test(key)) return "Replied";
  if (/(sent|emailed|warm-intro requested)/.test(key)) return "Sent";
  if (/applied/.test(key)) return "Applied";
  if (/draft/.test(key)) return "Drafts ready";
  if (/(contact|tiered|jd ingested|awaiting|target)/.test(key)) return "In progress";
  return "Discovered";
}

export function stagesByBucket(): Array<{ bucket: Bucket; stages: StageSpec[] }> {
  const groups = new Map<Bucket, StageSpec[]>();
  for (const s of STAGES) {
    if (!groups.has(s.bucket)) groups.set(s.bucket, []);
    groups.get(s.bucket)!.push(s);
  }
  return BUCKET_ORDER.filter((b) => groups.has(b)).map((bucket) => ({
    bucket,
    stages: groups.get(bucket)!,
  }));
}
