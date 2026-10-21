"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "~/lib/api";
import type { AssessmentUser } from "~/types/assessment";

const STORAGE_KEY = "scope-assessment-user-id";

const safeGetStoredUserId = () => {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};

/**
 * Stand-in for a login system: the selected user's id is sent to the API as
 * `X-User-Id`, and the backend resolves role and theater access from it.
 */
export function useMockSession() {
  const [users, setUsers] = useState<AssessmentUser[]>([]);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    api
      .listUsers()
      .then((loaded) => {
        setUsers(loaded);
        const stored = safeGetStoredUserId();
        setUserId(
          loaded.find((u) => u.id === stored)?.id ?? loaded[0]?.id ?? null,
        );
      })
      .catch((err: Error) => setUsersError(err.message));
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      if (userId) {
        window.localStorage.setItem(STORAGE_KEY, userId);
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // storage unavailable (private mode etc.)
    }
  }, [userId]);

  const user: AssessmentUser | null = useMemo(() => {
    if (!userId) return null;
    return users.find((candidate) => candidate.id === userId) ?? null;
  }, [userId, users]);

  return {
    users,
    usersError,
    user,
    userId,
    setUserId,
    signOut: () => setUserId(null),
  };
}
