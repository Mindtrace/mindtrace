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
import type { CameraService } from "@/lib/api/types";
import Link from "next/link";

export interface CameraServicesTableProps {
  items: CameraService[];
  onEdit?: (svc: CameraService) => void;
}

export function CameraServicesTable({
  items,
  onEdit,
}: CameraServicesTableProps) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="font-medium">Line</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Health</TableHead>
            <TableHead className="text-muted-foreground">Service URL</TableHead>
            <TableHead className="w-[160px] text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((c) => (
            <TableRow key={c.id}>
              <TableCell className="font-medium">
                {c.line_name ?? c.line_id}
              </TableCell>
              <TableCell>
                <span className="capitalize">{c.cam_service_status}</span>
              </TableCell>
              <TableCell>
                <span className="capitalize">{c.health_status}</span>
              </TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">
                {c.cam_service_url}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                  {onEdit ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onEdit(c)}
                    >
                      Edit
                    </Button>
                  ) : null}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
