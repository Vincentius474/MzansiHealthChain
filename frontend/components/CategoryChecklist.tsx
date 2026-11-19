"use client";
import { CATEGORY_LABELS, RecordCategory, RECORD_CATEGORIES } from "@/lib/workflow";

export default function CategoryChecklist({
  value,
  onChange,
  disabled = false,
}: {
  value: RecordCategory[];
  onChange: (categories: RecordCategory[]) => void;
  disabled?: boolean;
}) {
  function toggle(category: RecordCategory) {
    onChange(
      value.includes(category)
        ? value.filter((item) => item !== category)
        : [...value, category],
    );
  }

  return (
    <fieldset className="category-picker" disabled={disabled}>
      <legend>Record categories</legend>
      <div className="category-grid">
        {RECORD_CATEGORIES.map((category) => (
          <label key={category} className="check-label">
            <input
              type="checkbox"
              checked={value.includes(category)}
              onChange={() => toggle(category)}
            />
            {CATEGORY_LABELS[category]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
