export const RECORD_CATEGORIES = [
  "allergies",
  "diagnoses",
  "imaging",
  "lab_results",
  "medications",
  "visit_notes",
  "other",
] as const;

export type RecordCategory = (typeof RECORD_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<RecordCategory, string> = {
  allergies: "Allergies",
  diagnoses: "Diagnoses",
  imaging: "Imaging",
  lab_results: "Lab results",
  medications: "Medications",
  visit_notes: "Visit notes",
  other: "Other",
};
