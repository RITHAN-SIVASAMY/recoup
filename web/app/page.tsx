import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-2xl font-semibold">Recoup</h1>
      <p className="max-w-sm text-sm text-gray-500">
        Revenue recovery, measured honestly. This app serves both the merchant dashboard and
        signed, single-use customer recovery links at{" "}
        <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">/r/[token]</code>.
      </p>
      <Link
        href="/dashboard"
        className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
      >
        Open the dashboard
      </Link>
    </main>
  );
}
