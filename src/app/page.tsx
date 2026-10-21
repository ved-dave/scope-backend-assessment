"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "~/lib/api";
import { useDebounce } from "~/lib/hooks/useDebounce";
import { useMockSession } from "~/lib/mock-session";
import type {
  FilterOptions,
  MovieStatus,
  ShowtimePage,
  ShowtimeSortField,
  ShowtimeStatus,
  SortOrder,
  Theater,
  UploadPreview,
} from "~/types/assessment";
import { FileUpload } from "./_components/FileUpload";
import { FilterBar } from "./_components/FilterBar";
import { PreviewModal } from "./_components/PreviewModal";
import { ShowtimesTable } from "./_components/ShowtimesTable";

const movieStatusOptions: MovieStatus[] = [
  "approved",
  "draft",
  "flagged",
  "needs-review",
];

const emptyPage: ShowtimePage = {
  items: [],
  page: 1,
  pageSize: 50,
  total: 0,
  totalPages: 0,
};

const emptyFilterOptions: FilterOptions = {
  formats: [],
  languages: [],
  ratings: [],
  auditoriums: [],
  movieStatuses: [],
};

const PAGE_SIZE = 50;

export default function Home() {
  const { users, usersError, user, userId, setUserId, signOut } =
    useMockSession();
  const [accessibleTheaters, setAccessibleTheaters] = useState<Theater[]>([]);
  const [selectedTheaterId, setSelectedTheaterId] = useState<string>("all");
  const [showtimePage, setShowtimePage] = useState<ShowtimePage>(emptyPage);
  const [filterOptions, setFilterOptions] =
    useState<FilterOptions>(emptyFilterOptions);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebounce(searchQuery, 300);
  const [sortField, setSortField] = useState<ShowtimeSortField>("start_time");
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");
  const [page, setPage] = useState(1);

  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [preview, setPreview] = useState<UploadPreview | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [filters, setFilters] = useState({
    status: "all" as "active" | "inactive" | "archived" | "all",
    format: "",
    language: "",
    rating: "",
    auditorium: "",
    movieStatus: "",
    startDate: "",
    endDate: "",
  });

  const isAdmin = user?.role === "admin";
  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  // Any change to what's being queried starts back at page 1.
  useEffect(() => {
    setPage(1);
  }, [userId, selectedTheaterId, filters, debouncedSearchQuery, sortField, sortOrder]);

  useEffect(() => {
    setAccessibleTheaters([]);
    setSelectedTheaterId("all");
    // Non-admins can't sort/filter by movie status.
    setSortField((field) => (field === "movie_status" ? "start_time" : field));
    setFilters((current) => ({ ...current, movieStatus: "" }));
    if (!userId) return;
    api
      .listTheaters(userId)
      .then(setAccessibleTheaters)
      .catch((err: Error) => setError(err.message));
  }, [userId]);

  const theaterScope =
    selectedTheaterId === "all" ? undefined : [selectedTheaterId];

  useEffect(() => {
    if (!userId) {
      setShowtimePage(emptyPage);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    api
      .searchShowtimes(userId, {
        q: debouncedSearchQuery.trim() || undefined,
        status: filters.status === "all" ? undefined : filters.status,
        format: filters.format,
        language: filters.language,
        rating: filters.rating,
        movieStatus:
          isAdmin && filters.movieStatus
            ? (filters.movieStatus as MovieStatus)
            : undefined,
        startDate: filters.startDate,
        endDate: filters.endDate,
        auditorium: filters.auditorium ? [filters.auditorium] : undefined,
        theaterId: theaterScope,
        sort: sortField,
        order: sortOrder,
        page,
        pageSize: PAGE_SIZE,
      })
      .then((result) => {
        if (cancelled) return;
        setShowtimePage(result);
        setError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // theaterScope is derived from selectedTheaterId
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    userId,
    isAdmin,
    selectedTheaterId,
    filters,
    debouncedSearchQuery,
    sortField,
    sortOrder,
    page,
    reloadKey,
  ]);

  useEffect(() => {
    if (!userId) return;
    api
      .filterOptions(userId, theaterScope)
      .then(setFilterOptions)
      .catch(() => setFilterOptions(emptyFilterOptions));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, selectedTheaterId, reloadKey]);

  const handleFileSelect = async (file: File) => {
    if (!userId || selectedTheaterId === "all") return;
    setPreviewError(null);
    try {
      const staged = await api.uploadShowtimes(userId, file, selectedTheaterId);
      setPreview(staged);
      setIsPreviewOpen(true);
    } catch (err) {
      setError(`Upload failed: ${(err as Error).message}`);
    }
  };

  const handleConfirmChanges = async () => {
    if (!userId || !preview) return;
    setIsApplying(true);
    setPreviewError(null);
    try {
      await api.commitUpload(userId, preview.uploadId);
      setIsPreviewOpen(false);
      setPreview(null);
      reload();
    } catch (err) {
      setPreviewError((err as Error).message);
    } finally {
      setIsApplying(false);
    }
  };

  const handleClearSchedule = async () => {
    if (!userId) return;
    if (selectedTheaterId === "all") {
      alert("Select a single theater before clearing the schedule.");
      return;
    }
    if (
      !confirm(
        "Are you sure you want to archive all showtimes for this theater?",
      )
    ) {
      return;
    }
    try {
      await api.clearSchedule(userId, selectedTheaterId);
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const updateShowtime = async (
    showtimeId: string,
    patch: { movieStatus?: MovieStatus; status?: ShowtimeStatus },
  ) => {
    if (!userId) return;
    try {
      const updated = await api.updateShowtime(userId, showtimeId, patch);
      setShowtimePage((current) => ({
        ...current,
        items: current.items.map((showtime) =>
          showtime.id === updated.id ? updated : showtime,
        ),
      }));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const statusOptions = ["active", "inactive", "archived"] as const;

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#1a0b2e] to-[#0f0720]">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="mb-2 text-4xl font-bold text-white">
              Theater Showtimes Manager
            </h1>
            <p className="text-gray-400">
              Upload partner CSV files to manage showtimes
            </p>
          </div>

          <div className="w-full max-w-md rounded-lg border border-gray-700 bg-gray-900 p-4">
            <p className="text-xs uppercase text-gray-500">Session</p>
            <div className="mt-2 flex flex-col gap-3">
              <select
                value={userId ?? ""}
                onChange={(e) => setUserId(e.target.value)}
                className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value="" disabled>
                  Select a user
                </option>
                {users.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.name} ({candidate.role})
                  </option>
                ))}
              </select>
              {user ? (
                <div className="text-sm text-gray-400">
                  <div className="flex items-center justify-between">
                    <span>{user.email}</span>
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-medium ${
                        isAdmin
                          ? "bg-purple-900 text-purple-200"
                          : "bg-gray-700 text-gray-200"
                      }`}
                    >
                      {user.role}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    Theaters:{" "}
                    {user.canViewAll ? "All" : user.theaterIds.length || 0}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-gray-500">
                  No user selected.
                </div>
              )}
              <button
                onClick={signOut}
                className="rounded-lg border border-gray-600 px-3 py-2 text-xs font-semibold text-gray-300 transition hover:bg-gray-800"
              >
                Clear selection
              </button>
            </div>
          </div>
        </div>

        <div className="mb-6 flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold uppercase text-gray-400">
              Theater Scope
            </label>
            <select
              value={selectedTheaterId}
              onChange={(e) => setSelectedTheaterId(e.target.value)}
              disabled={!accessibleTheaters.length}
              className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            >
              <option value="all">All accessible theaters</option>
              {accessibleTheaters.map((theater) => (
                <option key={theater.id} value={theater.id}>
                  {theater.name}
                </option>
              ))}
            </select>
          </div>

          <FileUpload
            onFileSelect={handleFileSelect}
            disabled={
              !isAdmin ||
              selectedTheaterId === "all" ||
              accessibleTheaters.length === 0
            }
          />

          <button
            onClick={handleClearSchedule}
            disabled={
              !isAdmin ||
              selectedTheaterId === "all" ||
              accessibleTheaters.length === 0
            }
            className="rounded-lg border border-red-600 px-6 py-3 font-semibold text-red-400 transition hover:bg-red-950 disabled:opacity-50"
          >
            Clear Schedule
          </button>

          <div className="ml-auto text-sm text-gray-400">
            {showtimePage.total > 0 && (
              <>
                {showtimePage.total} showtimes
                {selectedTheaterId === "all" ? " across theaters" : ""}
              </>
            )}
          </div>
        </div>

        {!isAdmin && (
          <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-4 text-sm text-gray-400">
            You are in read-only mode. Admin users can upload CSVs and update
            movie status.
          </div>
        )}

        {(usersError ?? error) && (
          <div className="mb-6 rounded-lg border border-red-700 bg-red-950/40 p-4 text-sm text-red-300">
            {usersError
              ? `Could not reach the API: ${usersError}. Is the backend running on port 8000?`
              : error}
          </div>
        )}

        {accessibleTheaters.length === 0 ? (
          <div className="rounded-lg border border-gray-700 bg-gray-900 p-8 text-center text-gray-400">
            This user does not belong to any theaters yet.
          </div>
        ) : (
          <>
            <FilterBar
              status={filters.status}
              format={filters.format}
              language={filters.language}
              rating={filters.rating}
              auditorium={filters.auditorium}
              movieStatus={filters.movieStatus}
              startDate={filters.startDate}
              endDate={filters.endDate}
              onFilterChange={setFilters}
              availableFormats={filterOptions.formats}
              availableLanguages={filterOptions.languages}
              availableRatings={filterOptions.ratings}
              availableAuditoriums={filterOptions.auditoriums}
              availableMovieStatuses={isAdmin ? movieStatusOptions : []}
            />

            <div className="rounded-lg border border-gray-700 bg-gray-900 p-6">
              <ShowtimesTable
                showtimes={showtimePage.items}
                showTheaterColumn={selectedTheaterId === "all"}
                isAdmin={!!isAdmin}
                isLoading={isLoading}
                movieStatusOptions={movieStatusOptions}
                statusOptions={statusOptions}
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                sortField={sortField}
                sortOrder={sortOrder}
                onSortChange={(field, order) => {
                  setSortField(field);
                  setSortOrder(order);
                }}
                page={showtimePage.page}
                totalPages={showtimePage.totalPages}
                total={showtimePage.total}
                onPageChange={setPage}
                onMovieStatusChange={
                  isAdmin
                    ? (id, movieStatus) => updateShowtime(id, { movieStatus })
                    : undefined
                }
                onStatusChange={
                  isAdmin
                    ? (id, status) => updateShowtime(id, { status })
                    : undefined
                }
              />
            </div>
          </>
        )}

        <PreviewModal
          isOpen={isPreviewOpen}
          onClose={() => setIsPreviewOpen(false)}
          onConfirm={handleConfirmChanges}
          preview={preview}
          isApplying={isApplying}
          error={previewError}
        />
      </div>
    </main>
  );
}
