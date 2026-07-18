import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getCases, getChats, getProfile } from "../api/client";
import type { CaseSummary, ChatSummary, Profile } from "../api/types";
import { useSession } from "./session";

/**
 * Shared "Mein Mietfall" workspace state: the profile facts shown in the sidebar
 * and the user's Akten list. Centralised here (rather than living in each view's
 * local state) so any surface — chat, case list, document upload, contract review
 * — can refresh the sidebar by calling `refreshProfile()` / `refreshCases()`.
 */
interface WorkspaceState {
  profile: Profile | null;
  cases: CaseSummary[];
  chats: ChatSummary[];
  refreshProfile: () => void;
  refreshCases: () => void;
  refreshChats: () => void;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [chats, setChats] = useState<ChatSummary[]>([]);

  const refreshProfile = useCallback(() => {
    if (!user) return;
    getProfile()
      .then(setProfile)
      .catch(() => setProfile(null));
  }, [user]);

  const refreshCases = useCallback(() => {
    if (!user) return;
    getCases()
      .then(setCases)
      .catch(() => setCases([]));
  }, [user]);

  const refreshChats = useCallback(() => {
    if (!user) return;
    getChats()
      .then(setChats)
      .catch(() => setChats([]));
  }, [user]);

  // Load all on login; clear all on logout so a new user never sees stale data.
  useEffect(() => {
    if (!user) {
      setProfile(null);
      setCases([]);
      setChats([]);
      return;
    }
    refreshProfile();
    refreshCases();
    refreshChats();
  }, [user, refreshProfile, refreshCases, refreshChats]);

  return (
    <WorkspaceContext.Provider
      value={{ profile, cases, chats, refreshProfile, refreshCases, refreshChats }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
