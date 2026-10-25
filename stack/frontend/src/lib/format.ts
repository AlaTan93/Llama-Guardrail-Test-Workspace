/** Shared formatting helpers. */

export function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v}%`;
}

export function fmtTime(iso: string): string {
  return iso ? new Date(iso).toLocaleString() : "";
}

/** "attack_success" -> "ASR", "refusal" -> "REF" (display label). */
export function kindLabel(kind: string): string {
  return kind === "attack_success" ? "ASR" : "REF";
}
