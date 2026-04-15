"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  createStageGraph,
  getSafeErrorMessage,
  listStageGraphs,
} from "@/lib/api/client";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

export function StageGraphsPanel() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["stage-graphs"],
    queryFn: () => listStageGraphs({ limit: 500 }),
  });

  const createMutation = useMutation({
    mutationFn: async (name: string) => createStageGraph({ name }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["stage-graphs"] });
      toast.success("Stage graph created.");
      setShowCreate(false);
      setNewName("");
    },
    onError: (e: Error) => {
      toast.error(getSafeErrorMessage(e, "Failed to create stage graph."));
    },
  });

  if (isLoading) return <LoadingOverlay />;
  if (error) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-destructive">
            {getSafeErrorMessage(error, "Something went wrong.")}
          </p>
        </CardContent>
      </Card>
    );
  }

  const items = data?.items ?? [];
  return (
    <div className="space-y-4">
      <Dialog
        open={showCreate}
        onOpenChange={(open) => {
          setShowCreate(open);
          if (!open) setNewName("");
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create stage graph</DialogTitle>
            <DialogDescription>
              Pick a name now. You can add stages later in the editor.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="new-stage-graph-name">Name</Label>
            <Input
              id="new-stage-graph-name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. part-flow-a"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setShowCreate(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={createMutation.isPending || !newName.trim()}
              onClick={() => createMutation.mutate(newName.trim())}
            >
              {createMutation.isPending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="flex items-center justify-end">
        <Button variant="outline" onClick={() => setShowCreate(true)}>
          Create stage graph
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No stage graphs yet.
            </p>
          ) : (
            <div className="space-y-2">
              {items.map((g) => (
                <Link
                  key={g.id}
                  href={`/stage-graphs/${g.id}`}
                  className="flex items-center justify-between rounded-md border px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{g.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Stages: {g.stage_count}
                    </p>
                  </div>
                  <p className="font-mono text-xs text-muted-foreground">
                    {g.id}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
