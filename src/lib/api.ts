import type {
  AssessmentUser,
  FilterOptions,
  MovieStatus,
  Showtime,
  ShowtimePage,
  ShowtimeSortField,
  ShowtimeStatus,
  SortOrder,
  Theater,
  UploadPreview,
} from "~/types/assessment";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type QueryValue = string | number | string[] | undefined | null;

async function request<T>(
  path: string,
  {
    userId,
    query,
    ...init
  }: RequestInit & { userId?: string | null; query?: Record<string, QueryValue> } = {},
): Promise<T> {
  const url = new URL(path, API_URL);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    for (const v of Array.isArray(value) ? value : [value]) {
      url.searchParams.append(key, String(v));
    }
  }

  const headers = new Headers(init.headers);
  if (userId) headers.set("X-User-Id", userId);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export interface ShowtimeSearch {
  q?: string;
  status?: ShowtimeStatus;
  format?: string;
  language?: string;
  rating?: string;
  movieStatus?: MovieStatus;
  startDate?: string;
  endDate?: string;
  auditorium?: string[];
  theaterId?: string[];
  sort?: ShowtimeSortField;
  order?: SortOrder;
  page?: number;
  pageSize?: number;
}

export const api = {
  listUsers: () => request<AssessmentUser[]>("/users"),

  listTheaters: (userId: string) => request<Theater[]>("/theaters", { userId }),

  searchShowtimes: (userId: string, search: ShowtimeSearch) =>
    request<ShowtimePage>("/movies", {
      userId,
      query: {
        q: search.q,
        status: search.status,
        format: search.format,
        language: search.language,
        rating: search.rating,
        movie_status: search.movieStatus,
        start_date: search.startDate,
        end_date: search.endDate,
        auditorium: search.auditorium,
        theater_id: search.theaterId,
        sort: search.sort,
        order: search.order,
        page: search.page,
        page_size: search.pageSize,
      },
    }),

  filterOptions: (userId: string, theaterId?: string[]) =>
    request<FilterOptions>("/movies/filters", {
      userId,
      query: { theater_id: theaterId },
    }),

  updateShowtime: (
    userId: string,
    showtimeId: string,
    patch: { movieStatus?: MovieStatus; status?: ShowtimeStatus },
  ) =>
    request<Showtime>(`/showtimes/${showtimeId}`, {
      userId,
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  clearSchedule: (userId: string, theaterId: string) =>
    request<{ theaterId: string; archived: number }>(
      `/theaters/${theaterId}/clear-schedule`,
      { userId, method: "POST" },
    ),

  uploadShowtimes: (userId: string, file: File, theaterId?: string) => {
    const body = new FormData();
    body.append("file", file);
    return request<UploadPreview>("/uploadshowtime", {
      userId,
      method: "POST",
      body,
      query: { theater_id: theaterId },
    });
  },

  commitUpload: (userId: string, uploadId: string) =>
    request<UploadPreview>(`/uploads/${uploadId}/commit`, {
      userId,
      method: "POST",
    }),
};
