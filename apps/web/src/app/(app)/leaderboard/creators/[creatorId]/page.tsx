import { redirect } from "next/navigation";

export default async function LeaderboardCreatorRedirectPage({
  params,
}: {
  params: Promise<{ creatorId: string }>;
}) {
  const { creatorId } = await params;
  redirect(`/marketplace/creators/${creatorId}`);
}
