export type UserRole = "admin" | "user";
export type ShowtimeStatus = "active" | "inactive" | "archived";
export type MovieStatus = "approved" | "draft" | "flagged" | "needs-review";

export interface Theater {
  id: string;
  name: string;
  location: string;
  timezone: string;
}

export interface AssessmentUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  canViewAll: boolean;
  theaterIds: string[];
}

export interface Showtime {
  id: string;
  theaterId: string;
  theaterName: string;
  movieId: string;
  movieTitle: string;
  movieStatus: MovieStatus;
  auditorium: string;
  startTime: string;
  endTime: string;
  language: string;
  format: string;
  rating: string;
  lastUpdated: string;
  status: ShowtimeStatus;
}

export type ShowtimeSortField =
  | "title"
  | "start_time"
  | "end_time"
  | "last_updated"
  | "theater"
  | "movie_status";
export type SortOrder = "asc" | "desc";

export interface ShowtimePage {
  items: Showtime[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface FilterOptions {
  formats: string[];
  languages: string[];
  ratings: string[];
  auditoriums: string[];
  movieStatuses: MovieStatus[];
}

export interface FieldDiff {
  field: string;
  oldValue: string | null;
  newValue: string | null;
}

export type UploadChangeType =
  | "add"
  | "update"
  | "unchanged"
  | "archive"
  | "duplicate"
  | "invalid";

export interface UploadChange {
  type: UploadChangeType;
  rowNumber: number | null;
  showtimeId: string | null;
  theaterName: string;
  movieTitle: string;
  auditorium: string | null;
  startTime: string | null;
  endTime: string | null;
  language: string | null;
  format: string | null;
  rating: string | null;
  diffs: FieldDiff[];
  error: string | null;
}

export interface UploadSummary {
  totalRows: number;
  adds: number;
  updates: number;
  unchanged: number;
  archives: number;
  duplicates: number;
  invalid: number;
}

export interface UploadPreview {
  uploadId: string;
  status: "staged" | "committed" | "superseded";
  filename: string | null;
  theaterIds: string[];
  createdAt: string;
  committedAt: string | null;
  summary: UploadSummary;
  /** First N changes per type; the rest are paged via /uploads/{id}/changes. */
  samples: Partial<Record<UploadChangeType, UploadChange[]>>;
}
