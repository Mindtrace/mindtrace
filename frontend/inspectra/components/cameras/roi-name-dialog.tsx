"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

export function RoiNameDialog(props: {
  open: boolean;
  roiName: string;
  onRoiNameChange: (next: string) => void;
  canSubmit: boolean;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const { open, roiName, onRoiNameChange, canSubmit, onCancel, onSubmit } =
    props;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Name this ROI</DialogTitle>
          <DialogDescription>ROI name is required before saving.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="roi-name">ROI name</Label>
          <input
            id="roi-name"
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
            value={roiName}
            autoFocus
            onChange={(e) => onRoiNameChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== "Enter") return;
              if (!canSubmit) return;
              onSubmit();
            }}
            placeholder="e.g. inlet_box"
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" disabled={!canSubmit} onClick={onSubmit}>
            Add ROI
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

