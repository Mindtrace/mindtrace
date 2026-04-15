"use client";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Line, LineStatus } from "@/lib/api/types";

export function LinesTable(props: {
  lines: Line[];
  plantNameById: Map<string, string>;
  statusBadge: (s: LineStatus) => React.ReactNode;
  onEdit: (ln: Line) => void;
}) {
  const { lines, plantNameById, statusBadge, onEdit } = props;
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="font-medium">Name</TableHead>
            <TableHead>Plant</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {lines.map((ln) => (
            <TableRow key={ln.id}>
              <TableCell className="font-medium">{ln.name}</TableCell>
              <TableCell>{plantNameById.get(ln.plant_id) ?? ln.plant_id}</TableCell>
              <TableCell>{statusBadge(ln.status)}</TableCell>
              <TableCell className="text-right">
                <Button size="sm" variant="outline" onClick={() => onEdit(ln)}>
                  Edit
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

