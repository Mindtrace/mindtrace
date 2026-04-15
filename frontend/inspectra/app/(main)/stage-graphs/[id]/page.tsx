import { StageGraphEditor } from "@/components/stage-graphs/stage-graph-editor";

export default async function StageGraphDetailPage({
  params,
}: {
  params: Promise<{ id: string }> | { id: string };
}) {
  const resolved = await Promise.resolve(params);
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Stage graph</h1>
      <StageGraphEditor id={resolved.id} />
    </div>
  );
}
