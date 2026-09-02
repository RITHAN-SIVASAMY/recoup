import Link from "next/link";
import { CaseTimelineClient } from "./CaseTimelineClient";

export default async function CaseDetailPage({
  params,
}: {
  params: Promise<{ case_id: string }>;
}) {
  const { case_id } = await params;
  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <Link href="/dashboard" className="text-sm text-[var(--color-accent)] hover:underline">
        ← back to dashboard
      </Link>
      <h1 className="mt-2 mb-6 text-xl font-semibold">Case {case_id}</h1>
      <CaseTimelineClient caseId={case_id} />
    </main>
  );
}
