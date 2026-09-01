import { SimulatePaymentClient } from "./SimulatePaymentClient";

export default async function SimulatePaymentPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <SimulatePaymentClient token={token} />;
}
