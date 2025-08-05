import os
import pandas as pd
import json
from tqdm import tqdm
from shutil import copy2
from PIL import Image, ImageDraw, ImageFont

# --- Config ---
EXCEL_FILE = "/home/vineeth/10492LaserWelderDefects 7-30-25.xlsx"
SEARCH_DIR = "/data/nfs/datasets/laser/New Set"
OUTPUT_FILE = "matched_serials.json"

DEST_ANNOTATED_DIR = "matched_images"
DEST_ORIGINAL_DIR = "matched_originals"

SERIAL_COLUMN = "SerialNumber"
WELD_COLUMN = "WeldName"
DEFECT_COLUMN = "WeldDefect"

# --- Step 1: Load Excel ---
df = pd.read_excel(EXCEL_FILE)
df = df.dropna(subset=[SERIAL_COLUMN])
df[SERIAL_COLUMN] = df[SERIAL_COLUMN].astype(str)
df[WELD_COLUMN] = df[WELD_COLUMN].astype(str)
df[DEFECT_COLUMN] = df[DEFECT_COLUMN].astype(str)

# Create lookup dict: (serial, weld) -> defect
pair_to_defect = {
    (row[SERIAL_COLUMN], row[WELD_COLUMN]): row[DEFECT_COLUMN]
    for _, row in df.iterrows()
}

serial_weld_pairs = list(pair_to_defect.keys())

# --- Step 2: Gather all files ---
all_file_paths = []
for root, _, files in os.walk(SEARCH_DIR):
    for fname in files:
        all_file_paths.append(os.path.join(root, fname))

# --- Step 3: Match + Copy + Annotate ---
serial_only_matches = {}
serial_and_weld_matches = {}

def overlay_defect_text(img_path, defect_text, output_path):
    try:
        image = Image.open(img_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except IOError:
            font = ImageFont.load_default()

        draw.text((10, 10), f"Defect: {defect_text}", fill="red", font=font)
        image.save(output_path)
    except Exception as e:
        print(f"⚠️ Failed to process image {img_path}: {e}")

for file_path in tqdm(all_file_paths, desc="Matching, copying, and annotating"):
    fname = os.path.basename(file_path)

    for serial, weld in serial_weld_pairs:
        if serial in fname:
            defect = pair_to_defect.get((serial, weld), "UNKNOWN")

            # --- Serial-only match ---
            serial_only_matches.setdefault(serial, []).append(file_path)

            # Annotated image copy
            annotated_dest = os.path.join(DEST_ANNOTATED_DIR, "serial_only", fname)
            os.makedirs(os.path.dirname(annotated_dest), exist_ok=True)
            overlay_defect_text(file_path, defect, annotated_dest)

            # Original image copy
            original_dest = os.path.join(DEST_ORIGINAL_DIR, "serial_only", fname)
            os.makedirs(os.path.dirname(original_dest), exist_ok=True)
            copy2(file_path, original_dest)

            # --- Serial + Weld match ---
            if weld and weld in fname:
                serial_and_weld_matches.setdefault(serial, []).append(file_path)

                # Annotated
                annotated_dest_weld = os.path.join(DEST_ANNOTATED_DIR, "serial_and_weld", fname)
                os.makedirs(os.path.dirname(annotated_dest_weld), exist_ok=True)
                overlay_defect_text(file_path, defect, annotated_dest_weld)

                # Original
                original_dest_weld = os.path.join(DEST_ORIGINAL_DIR, "serial_and_weld", fname)
                os.makedirs(os.path.dirname(original_dest_weld), exist_ok=True)
                copy2(file_path, original_dest_weld)

            break  # Already matched this file

# --- Step 4: Save JSON results ---
output = {
    "serial_only_matches": serial_only_matches,
    "serial_and_weld_matches": serial_and_weld_matches
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(output, f, indent=2)

# --- Step 5: Summary ---
print(f"\n✅ Done.")
print(f"🔹 Serial-only matches: {len(serial_only_matches)} serial numbers matched.")
print(f"🔸 Serial + Weld matches: {len(serial_and_weld_matches)} serial numbers matched.")
print(f"🖼️ Annotated images saved to: {DEST_ANNOTATED_DIR}/")
print(f"🗃️ Original images copied to: {DEST_ORIGINAL_DIR}/")
print(f"📝 Match metadata saved to: {OUTPUT_FILE}")
