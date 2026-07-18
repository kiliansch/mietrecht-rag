import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { patchPersona, setOnUnauthorized, setToken } from "../api/client";
import type { AuthUser, Role } from "../api/types";

interface SessionState {
  user: AuthUser | null;
  /** Legal persona sent with chat requests (mieter/vermieter/jurist). */
  role: string;
  model: string;
  /** UI + answer language ("de" | "en"). */
  language: string;
  threadId: string;
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
  setRole: (r: Role) => void;
  setModel: (model: string) => void;
  setLanguage: (l: string) => void;
  newThread: () => void;
  setThread: (id: string) => void;
}

const SessionContext = createContext<SessionState | null>(null);

const newId = () => crypto.randomUUID();

const loadUser = (): AuthUser | null => {
  // Only trust the cache when a token exists; the server re-validates every call.
  if (!localStorage.getItem("token")) return null;
  try {
    return JSON.parse(localStorage.getItem("user") ?? "null") as AuthUser | null;
  } catch {
    return null;
  }
};

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(loadUser);
  const [role, setRoleState] = useState(() => loadUser()?.persona ?? "mieter");
  const [model, setModelState] = useState(() => localStorage.getItem("model") ?? "");
  const [language, setLanguageState] = useState(() => localStorage.getItem("lang") ?? "de");
  const [threadId, setThreadId] = useState<string>(newId);

  const login = useCallback((token: string, u: AuthUser) => {
    setToken(token);
    localStorage.setItem("user", JSON.stringify(u));
    setUser(u);
    setRoleState(u.persona);
    setThreadId(newId());
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    localStorage.removeItem("user");
    setUser(null);
  }, []);

  // Any 401 from the API forces a clean logout (expired/revoked token).
  useEffect(() => {
    setOnUnauthorized(() => logout());
    return () => setOnUnauthorized(null);
  }, [logout]);

  const setRole = useCallback(
    (r: Role) => {
      setRoleState(r);
      setUser((prev) => {
        const next = prev ? { ...prev, persona: r } : prev;
        if (next) localStorage.setItem("user", JSON.stringify(next));
        return next;
      });
      patchPersona(r).catch(() => undefined); // persisted server-side, best-effort
    },
    [],
  );

  const setModel = useCallback((m: string) => {
    setModelState(m);
    localStorage.setItem("model", m);
  }, []);

  const setLanguage = useCallback((l: string) => {
    setLanguageState(l);
    localStorage.setItem("lang", l);
  }, []);

  const newThread = useCallback(() => setThreadId(newId()), []);
  const setThread = useCallback((id: string) => setThreadId(id), []);

  return (
    <SessionContext.Provider
      value={{
        user, role, model, language, threadId,
        login, logout, setRole, setModel, setLanguage, newThread, setThread,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
