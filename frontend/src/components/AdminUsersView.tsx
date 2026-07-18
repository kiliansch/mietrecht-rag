import { useCallback, useEffect, useState } from "react";
import { createUser, getUsers, setUserActive } from "../api/client";
import type { UserAccount } from "../api/types";
import { useSession } from "../state/session";
import { useT } from "../i18n";
import { Icon } from "./Icon";

export function AdminUsersView() {
  const { user: me } = useSession();
  const t = useT();
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Create form
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    getUsers()
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(refresh, [refresh]);

  const submit = async () => {
    if (!username.trim() || !password || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createUser({
        username: username.trim(),
        display_name: displayName.trim(),
        password,
        role,
      });
      setNotice(t("admin.userCreated", { name: created.username }));
      setUsername("");
      setDisplayName("");
      setPassword("");
      setRole("user");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (u: UserAccount) => {
    setError(null);
    try {
      await setUserActive(u.username, !u.is_active);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-8">
      <div>
        <h2 className="text-2xl font-bold text-primary">{t("admin.title")}</h2>
        <p className="mt-1 text-on-surface-variant">{t("admin.subtitle")}</p>
      </div>

      {error && (
        <p className="rounded-lg bg-error-container px-4 py-3 text-sm text-on-error-container">❌ {error}</p>
      )}
      {notice && (
        <p className="rounded-lg bg-success-container/40 px-4 py-3 text-sm text-on-success-container">
          ✅ {notice}
        </p>
      )}

      {/* Create form */}
      <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-card">
        <p className="mb-4 font-semibold">
          <Icon name="person_add" className="mr-1 align-middle text-base" /> {t("admin.newAccount")}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="font-medium">{t("admin.username")}</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("admin.usernamePlaceholder")}
              className="mt-1 w-full rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">{t("admin.displayName")}</span>
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={t("admin.displayNamePlaceholder")}
              className="mt-1 w-full rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">{t("admin.password")}</span>
            <input
              type="password"
              value={password}
              autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">{t("admin.role")}</span>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as "user" | "admin")}
              className="mt-1 w-full rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
            >
              <option value="user">{t("admin.roleUser")}</option>
              <option value="admin">{t("admin.roleAdmin")}</option>
            </select>
          </label>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            onClick={submit}
            disabled={!username.trim() || password.length < 8 || busy}
            className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? t("admin.creating") : t("admin.createAccount")}
          </button>
        </div>
      </div>

      {/* User table */}
      <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest shadow-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-on-surface-variant">
              <th className="px-4 py-3 font-medium">{t("admin.colUser")}</th>
              <th className="px-4 py-3 font-medium">{t("admin.colRole")}</th>
              <th className="px-4 py-3 font-medium">{t("admin.colStatus")}</th>
              <th className="px-4 py-3 text-right font-medium">{t("admin.colAction")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username} className="border-t border-outline-variant">
                <td className="px-4 py-3">
                  <p className="font-medium">{u.display_name}</p>
                  <p className="text-xs text-on-surface-variant">@{u.username}</p>
                </td>
                <td className="px-4 py-3">{u.role === "admin" ? t("admin.roleAdmin") : t("admin.roleUser")}</td>
                <td className="px-4 py-3">
                  {u.is_active ? (
                    <span className="rounded-full bg-success-container/40 px-2 py-0.5 text-xs text-on-success-container">
                      {t("admin.active")}
                    </span>
                  ) : (
                    <span className="rounded-full bg-error-container px-2 py-0.5 text-xs text-on-error-container">
                      {t("admin.inactive")}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {u.username !== me?.username && (
                    <button
                      onClick={() => toggleActive(u)}
                      className={`text-xs hover:underline ${u.is_active ? "text-error" : "text-primary"}`}
                    >
                      {u.is_active ? t("admin.deactivate") : t("admin.activate")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-on-surface-variant">
                  {t("admin.noUsers")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
