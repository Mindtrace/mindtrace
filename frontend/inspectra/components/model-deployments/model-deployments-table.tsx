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
import type { ModelDeployment } from "@/lib/api/types";

export interface ModelDeploymentsTableProps {
  items: ModelDeployment[];
  onEdit?: (deployment: ModelDeployment) => void;
}

export function ModelDeploymentsTable({
  items,
  onEdit,
}: ModelDeploymentsTableProps) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="font-medium">Line</TableHead>
            <TableHead>Plant</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Health</TableHead>
            <TableHead className="text-muted-foreground">Server URL</TableHead>
            {onEdit ? (
              <TableHead className="w-[80px] text-right">Actions</TableHead>
            ) : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((d) => (
            <TableRow key={d.id}>
              <TableCell className="font-medium">
                {d.line_name ?? d.line_id}
              </TableCell>
              <TableCell>{d.plant_name ?? d.plant_id}</TableCell>
              <TableCell>{d.model_name ?? d.model_id}</TableCell>
              <TableCell>
                <span className="capitalize">{d.deployment_status}</span>
              </TableCell>
              <TableCell>
                <span className="capitalize">{d.health_status}</span>
              </TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">
                {d.model_server_url}
              </TableCell>
              {onEdit ? (
                <TableCell className="text-right">
                  <Button size="sm" variant="outline" onClick={() => onEdit(d)}>
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
