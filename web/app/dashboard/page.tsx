import { DashboardClient } from "./DashboardClient";

export default function DashboardPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">Recoup</h1>
          <p className="text-sm text-black/50">Revenue recovery, measured honestly.</p>
        </div>
      </header>
      <DashboardClient />
    </main>
  );
}
