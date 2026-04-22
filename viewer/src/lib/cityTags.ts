// Canonical city buckets + the order in which they should appear in filter
// dropdowns. Hybrid locations like "SF, Seattle, New York, Remote in the US"
// belong to *every* bucket they match, so selecting any one of those filters
// keeps that row visible.
export const CITY_ORDER = [
  "NYC",
  "Bay Area",
  "Seattle",
  "Boston",
  "Other US",
  "Remote",
  "Unknown",
] as const;

export type CityBucket = (typeof CITY_ORDER)[number];

const PATTERNS: Array<[CityBucket, RegExp]> = [
  ["NYC", /new york|\bnyc\b|brooklyn|union square|manhattan/i],
  ["Bay Area", /san francisco|\bsf\b|mountain view|palo alto|burlingame|bay area/i],
  ["Seattle", /seattle/i],
  ["Boston", /boston/i],
  [
    "Other US",
    /pittsburgh|chicago|los angeles|\blos\s*angeles\b|washington(,|\s+d)|\bd\.?c\.?\b|united states|\bus\b|\busa\b|americas|north america/i,
  ],
  ["Remote", /remote/i],
];

export function cityTags(location: string): CityBucket[] {
  if (!location) return ["Unknown"];
  const tags = new Set<CityBucket>();
  for (const [bucket, re] of PATTERNS) {
    if (re.test(location)) tags.add(bucket);
  }
  // Demote "Other US" when a more specific US city already matched — the
  // user picking "NYC" shouldn't also pull in the "Other US" bucket for a
  // row that's actually in NYC.
  const specificUS: CityBucket[] = ["NYC", "Bay Area", "Seattle", "Boston"];
  if (specificUS.some((b) => tags.has(b))) tags.delete("Other US");
  if (tags.size === 0) tags.add("Unknown");
  return CITY_ORDER.filter((b) => tags.has(b));
}
