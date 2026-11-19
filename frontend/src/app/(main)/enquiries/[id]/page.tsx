import { Suspense } from "react";
import { EnquiryClient } from "./EnquiryClient";

export const revalidate = 0;
export function generateStaticParams() {
  return [];
}

export default function Page() {
  return <Suspense><EnquiryClient /></Suspense>;
}
