// ./mongo-seed/seed.js
// Seed three collections: welds, parts, image
// - welds: { name, camera_id, defect, image_id }
// - parts: { serial_number, analytic_id }
// - image: { camera_id, image_id, analytic_id }

// Helpers
function getDefectForCamera(cameraIndexOneBased) {
  // Cameras 6..9 get specific defects, others are Healthy
  if (cameraIndexOneBased === 6) return "burnthrough";
  if (cameraIndexOneBased === 7) return "missing";
  if (cameraIndexOneBased === 8) return "cold_weld";
  if (cameraIndexOneBased === 9) return "spatter";
  return "Healthy";
}

function getAnalyticIdForImage(imageIndexOneBased) {
  // Map images to analytic groups, matching the screenshots
  if (imageIndexOneBased >= 1 && imageIndexOneBased <= 11) return 4567;
  if (imageIndexOneBased >= 12 && imageIndexOneBased <= 22) return 4568;
  if (imageIndexOneBased >= 23 && imageIndexOneBased <= 33) return 4569;
  return 4570; // 34..44
}

const dbName = db.getSiblingDB("demo");

// Clean previous data (idempotent seeding)
dbName.welds.deleteMany({});
dbName.parts.deleteMany({});
dbName.image.deleteMany({});

// Parts collection (Serial Number -> Analytic_Id)
const parts = [
  { serial_number: "12345", analytic_id: 4567 },
  { serial_number: "12346", analytic_id: 4568 },
  { serial_number: "12347", analytic_id: 4569 },
  { serial_number: "12348", analytic_id: 4570 },
];

// Image collection (camera_id, image_id, Analytic_Id)
const imageDocs = [];
// Generate 44 images across 12 cameras (cycling), grouped into 4 analytics
for (let i = 1; i <= 44; i++) {
  const camIdx = ((i - 1) % 12) + 1; // 1..12
  imageDocs.push({
    camera_id: `cam${camIdx}`,
    image_id: `image${i}`,
    analytic_id: getAnalyticIdForImage(i),
  });
}

// Welds collection (name, camera_id, defect, image_id)
const welds = [];
for (let i = 1; i <= 44; i++) {
  const camIdx = ((i - 1) % 12) + 1; // 1..12
  const weldIdx = ((i - 1) % 12) + 1; // IBWA1..IBWA12 cycling
  welds.push({
    name: `IBWA${weldIdx}`,
    camera_id: `cam${camIdx}`,
    defect: getDefectForCamera(camIdx),
    image_id: `image${i}`,
  });
}

// Insert into MongoDB
dbName.parts.insertMany(parts);
dbName.image.insertMany(imageDocs);
dbName.welds.insertMany(welds);