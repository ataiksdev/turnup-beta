"use client";
import { useOfflineImage } from "@/lib/offlineImages";

/** A plain <img> that uses the kept copy of the photo while offline (see lib/offlineImages). */
export function OfflineImg({ src, ...rest }: React.ImgHTMLAttributes<HTMLImageElement> & { src?: string | null }) {
  const shown = useOfflineImage(src);
  // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
  return shown ? <img src={shown} {...rest} /> : null;
}
