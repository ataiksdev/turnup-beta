import CheckInPageClient from "./CheckInPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <CheckInPageClient />;
}
