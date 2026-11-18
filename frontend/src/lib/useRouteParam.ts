"use client";
import { useParams, useSearchParams } from "next/navigation";

/**
 * Reads a page's id/slug/username whether it arrived as a path segment (/events/abc, the web
 * build) or a query parameter (/events/view?id=abc, the Capacitor build; see lib/routes.ts).
 *
 * Components calling this must sit under a <Suspense> boundary (useSearchParams requires it
 * for statically rendered pages).
 */
export function useRouteParam(name: string): string {
  const params = useParams<Record<string, string | string[]>>();
  const search = useSearchParams();
  const raw = params?.[name];
  const fromPath = Array.isArray(raw) ? raw[0] : raw;
  if (fromPath) {
    try {
      return decodeURIComponent(fromPath);
    } catch {
      return fromPath;
    }
  }
  return search?.get(name) ?? "";
}
