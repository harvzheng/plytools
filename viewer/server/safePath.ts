import { realpathSync } from "node:fs";

// Returns true iff `candidate` resolves (via realpath) to a path inside `root`.
// Returns false for missing paths, paths outside root, and symlinks that escape root.
export function isInside(root: string, candidate: string): boolean {
  let resolvedRoot: string;
  let resolvedCandidate: string;
  try {
    resolvedRoot = realpathSync(root);
    resolvedCandidate = realpathSync(candidate);
  } catch {
    return false;
  }
  const rootWithSep = resolvedRoot.endsWith("/")
    ? resolvedRoot
    : resolvedRoot + "/";
  return (
    resolvedCandidate === resolvedRoot ||
    resolvedCandidate.startsWith(rootWithSep)
  );
}
