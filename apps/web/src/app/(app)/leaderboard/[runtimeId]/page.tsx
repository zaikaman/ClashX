import { redirect } from "next/navigation";

export default async function LeaderboardRuntimeRedirectPage({
  params,
}: {
  params: Promise<{ runtimeId: string }>;
}) {
  const { runtimeId } = await params;
  redirect(`/marketplace/${runtimeId}`);
}
