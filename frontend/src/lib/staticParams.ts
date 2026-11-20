/**
 * generateStaticParams for the dynamic pages (/events/[id], /tickets/[id], ...).
 *
 * Website build: no pages ahead of time; each one renders when it's visited.
 * Android app build (static export): the app reaches these screens through its /…/view?id=
 * pages instead, but Next.js 16.3+ refuses a dynamic page that exports nothing ("returned an
 * empty array from generateStaticParams()"). So the export gets one placeholder copy of each,
 * which scripts/strip-admin.js deletes afterwards.
 */
export const STATIC_PLACEHOLDER = "__placeholder";

export function staticParams<K extends string>(...keys: K[]): Record<K, string>[] {
  if (process.env.CAPACITOR_BUILD !== "true") return [];
  return [Object.fromEntries(keys.map((k) => [k, STATIC_PLACEHOLDER])) as Record<K, string>];
}
