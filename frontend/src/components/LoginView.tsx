import { useState } from "react";
import { postLogin } from "../api/client";
import type { AppConfig } from "../api/types";
import { useSession } from "../state/session";
import { useT } from "../i18n";

export function LoginView({ config }: { config: AppConfig }) {
  const { login, setModel } = useSession();
  const t = useT();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!username.trim() || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await postLogin(username.trim(), password);
      if (!localStorage.getItem("model") && config.models[0]) {
        setModel(config.models[0].value);
      }
      login(res.token, res.user);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-surface-container-high text-3xl">
        ⚖️
      </div>
      <div className="w-full max-w-md rounded-2xl border border-outline-variant bg-surface-container-lowest p-8 shadow-card sm:p-10">
        <h1 className="text-center text-3xl font-bold leading-tight text-primary">
          {t("app.title")}
        </h1>
        <p className="mt-3 text-center text-on-surface-variant">
          {t("login.subtitle")}
        </p>
        <hr className="my-7 border-outline-variant" />

        <label className="block text-sm font-medium" htmlFor="username">
          {t("login.username")}
        </label>
        <input
          id="username"
          value={username}
          autoComplete="username"
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="benutzername"
          className="mt-2 w-full rounded-lg border-outline-variant focus:border-primary focus:ring-primary"
        />

        <label className="mt-4 block text-sm font-medium" htmlFor="password">
          {t("login.password")}
        </label>
        <input
          id="password"
          type="password"
          value={password}
          autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="••••••••"
          className="mt-2 w-full rounded-lg border-outline-variant focus:border-primary focus:ring-primary"
        />

        {error && (
          <p className="mt-4 rounded-lg bg-error-container px-4 py-3 text-sm text-on-error-container">
            {error}
          </p>
        )}

        <div className="mt-8">
          <button
            onClick={submit}
            disabled={!username.trim() || !password || busy}
            className="w-full rounded-lg bg-primary px-8 py-2.5 font-medium text-on-primary shadow-card transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? t("login.busy") : t("login.submit")}
          </button>
        </div>

        <p className="mt-4 text-center text-xs text-on-surface-variant">
          {t("login.noAccount")}
        </p>
      </div>
    </div>
  );
}
