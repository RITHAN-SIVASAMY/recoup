export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-2 px-6 text-center">
      <h1 className="text-2xl font-semibold">Recoup</h1>
      <p className="max-w-sm text-sm text-gray-500">
        This is the merchant recovery agent&apos;s public site. The dashboard lands in Phase 11 —
        for now, this app only serves signed, single-use recovery links at{" "}
        <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">/r/[token]</code>.
      </p>
    </main>
  );
}
