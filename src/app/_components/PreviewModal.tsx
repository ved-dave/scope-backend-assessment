"use client";

import type { UploadChange, UploadPreview } from "~/types/assessment";

interface PreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  preview: UploadPreview | null;
  isApplying: boolean;
  error: string | null;
}

const formatDateTime = (dateStr: string | null) => {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

interface SectionProps {
  title: string;
  count: number;
  items: UploadChange[];
  tone: "green" | "yellow" | "red" | "gray";
  renderDetail: (change: UploadChange) => React.ReactNode;
}

const toneClasses = {
  green: {
    heading: "text-green-400",
    badge: "bg-green-900",
    card: "border-green-900 bg-green-950/30",
  },
  yellow: {
    heading: "text-yellow-400",
    badge: "bg-yellow-900",
    card: "border-yellow-900 bg-yellow-950/30",
  },
  red: {
    heading: "text-red-400",
    badge: "bg-red-900",
    card: "border-red-900 bg-red-950/30",
  },
  gray: {
    heading: "text-gray-300",
    badge: "bg-gray-700",
    card: "border-gray-700 bg-gray-800/40",
  },
};

function Section({ title, count, items, tone, renderDetail }: SectionProps) {
  if (count === 0) return null;
  const classes = toneClasses[tone];
  return (
    <div>
      <h3
        className={`mb-3 flex items-center text-lg font-semibold ${classes.heading}`}
      >
        <span
          className={`mr-2 flex h-6 min-w-6 items-center justify-center rounded-full px-1.5 text-xs ${classes.badge}`}
        >
          {count}
        </span>
        {title}
        {items.length < count && (
          <span className="ml-2 text-xs font-normal text-gray-500">
            (showing first {items.length})
          </span>
        )}
      </h3>
      <div className="space-y-2">
        {items.map((change, idx) => (
          <div
            key={change.showtimeId ?? change.rowNumber ?? idx}
            className={`rounded-lg border p-4 ${classes.card}`}
          >
            <div className="font-semibold text-white">{change.movieTitle}</div>
            <div className="mt-1 text-sm text-gray-300">
              {formatDateTime(change.startTime)} –{" "}
              {formatDateTime(change.endTime)}
            </div>
            {renderDetail(change)}
          </div>
        ))}
      </div>
    </div>
  );
}

export function PreviewModal({
  isOpen,
  onClose,
  onConfirm,
  preview,
  isApplying,
  error,
}: PreviewModalProps) {
  if (!isOpen || !preview) return null;

  const { summary, samples } = preview;
  const totalChanges = summary.adds + summary.updates + summary.archives;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-xl bg-gray-900 shadow-2xl">
        <div className="sticky top-0 z-10 border-b border-gray-700 bg-gray-900 px-6 py-4">
          <h2 className="text-2xl font-bold text-white">
            Preview Changes
            {totalChanges > 0 && (
              <span className="ml-2 text-sm text-gray-400">
                ({totalChanges} total)
              </span>
            )}
          </h2>
          <p className="mt-1 text-sm text-gray-400">
            {preview.filename ?? "Upload"} · {summary.totalRows} rows ·{" "}
            {summary.unchanged} unchanged
          </p>
        </div>

        <div className="p-6">
          {error && (
            <div className="mb-4 rounded-lg border border-red-700 bg-red-950/40 p-3 text-sm text-red-300">
              {error}
            </div>
          )}
          {totalChanges === 0 && summary.invalid === 0 ? (
            <p className="text-center text-gray-400">
              No changes detected. The schedule is already up to date.
            </p>
          ) : (
            <div className="space-y-6">
              <Section
                title="New Showtimes"
                count={summary.adds}
                items={samples.add ?? []}
                tone="green"
                renderDetail={(add) => (
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-400">
                    <span>{add.auditorium}</span>
                    <span>•</span>
                    <span>{add.language}</span>
                    <span>•</span>
                    <span>{add.format}</span>
                    <span>•</span>
                    <span>{add.rating}</span>
                  </div>
                )}
              />

              <Section
                title="Updated Showtimes"
                count={summary.updates}
                items={samples.update ?? []}
                tone="yellow"
                renderDetail={(update) => (
                  <div className="mt-2 space-y-1">
                    {update.diffs.map((diff, idx) => (
                      <div key={idx} className="text-sm">
                        <span className="text-gray-400">{diff.field}:</span>{" "}
                        <span className="text-red-400 line-through">
                          {diff.oldValue}
                        </span>{" "}
                        →{" "}
                        <span className="text-green-400">{diff.newValue}</span>
                      </div>
                    ))}
                  </div>
                )}
              />

              <Section
                title="Archived Showtimes"
                count={summary.archives}
                items={samples.archive ?? []}
                tone="red"
                renderDetail={() => (
                  <div className="mt-1 text-xs text-gray-400">
                    Not present in new drop · will be flagged for review
                  </div>
                )}
              />

              <Section
                title="Duplicate Rows (ignored)"
                count={summary.duplicates}
                items={samples.duplicate ?? []}
                tone="gray"
                renderDetail={(dup) => (
                  <div className="mt-1 text-xs text-gray-400">
                    Row {dup.rowNumber} · a later row for the same showtime
                    was kept
                  </div>
                )}
              />

              <Section
                title="Invalid Rows (skipped)"
                count={summary.invalid}
                items={samples.invalid ?? []}
                tone="gray"
                renderDetail={(bad) => (
                  <div className="mt-1 text-xs text-red-300">
                    Row {bad.rowNumber}: {bad.error}
                  </div>
                )}
              />
            </div>
          )}
        </div>

        <div className="sticky bottom-0 border-t border-gray-700 bg-gray-900 px-6 py-4">
          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              disabled={isApplying}
              className="rounded-lg border border-gray-600 px-6 py-2 font-medium text-white transition hover:bg-gray-800 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={isApplying || totalChanges === 0}
              className="rounded-lg bg-purple-600 px-6 py-2 font-medium text-white transition hover:bg-purple-700 disabled:opacity-50"
            >
              {isApplying ? "Applying..." : "Confirm Changes"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
