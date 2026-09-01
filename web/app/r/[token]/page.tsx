import { fetchRecoveryContext } from "@/lib/api";
import { RecoveryClient } from "./RecoveryClient";

function ProblemPage({ status, detail }: { status: number; detail: string }) {
  const title = status === 409 ? "This link has already been used" : "This link isn't valid";
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="max-w-sm text-sm text-gray-500">{detail}</p>
      <p className="max-w-sm text-xs text-gray-400">
        If you still need help with this payment, please contact the merchant directly.
      </p>
    </main>
  );
}

export default async function RecoveryPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const result = await fetchRecoveryContext(token);

  if (!result.ok) {
    return <ProblemPage status={result.error.status} detail={result.error.detail} />;
  }

  return <RecoveryClient token={token} context={result.data} />;
}
