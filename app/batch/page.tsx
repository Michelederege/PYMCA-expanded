import { BatchApp } from "@/components/batch-app";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Batch",
  description: "Run one fit configuration over a list of scans.",
};

export default function BatchPage() {
  return <BatchApp />;
}
