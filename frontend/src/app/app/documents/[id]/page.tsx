import { DocumentDetailClient } from "./_client";

export default async function DocumentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DocumentDetailClient id={Number(id)} />;
}
