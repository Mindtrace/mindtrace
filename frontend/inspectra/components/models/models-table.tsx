"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import type { Model } from "@/lib/api/types";

export interface ModelsTableProps {
  items: Model[];
  onEdit?: (model: Model) => void;
}

export function ModelsTable({ items, onEdit }: ModelsTableProps) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="font-medium">Name</TableHead>
            <TableHead>Version</TableHead>
            <TableHead className="text-muted-foreground">Version ID</TableHead>
            {onEdit ? (
              <TableHead className="w-[80px] text-right">Actions</TableHead>
            ) : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((model) => (
            <TableRow key={model.id}>
              <TableCell className="font-medium">{model.name}</TableCell>
              <TableCell>{model.version ?? "—"}</TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">
                {model.version_id ?? "—"}
              </TableCell>
              {onEdit ? (
                <TableCell className="text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onEdit(model)}
                  >
                    Edit
                  </Button>
                </TableCell>
              ) : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
