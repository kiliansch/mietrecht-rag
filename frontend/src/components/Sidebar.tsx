import { deleteChat } from "../api/client";
import type { AppConfig, ChatMessage, Role } from "../api/types";
import type { TokenTotals } from "../state/useChat";
import { useSession } from "../state/session";
import { useWorkspace } from "../state/workspace";
import { useT } from "../i18n";
import { Icon } from "./Icon";
import { MietfallPanel } from "./MietfallPanel";
import { ExportMenu } from "./ExportMenu";

export type Tab = "chat" | "cases" | "eval" | "users";

const isOverdue = (iso: string) => iso < new Date().toISOString().slice(0, 10);

// Tab labels come from i18n (`nav.<id>`); this table only holds id + icon.
const TABS: { id: Tab; icon: string; adminOnly?: boolean }[] = [
  { id: "chat", icon: "chat" },
  { id: "cases", icon: "folder" },
  { id: "eval", icon: "bar_chart", adminOnly: true },
  { id: "users", icon: "group", adminOnly: true },
];

interface Props {
  config: AppConfig;
  activeTab: Tab;
  onTab: (t: Tab) => void;
  messages: ChatMessage[];
  tokens: TokenTotals;
  onOpenCase: (caseId: string) => void;
  onOpenChat: (threadId: string) => void;
  onNewChat: () => void;
}

export function Sidebar({
  config, activeTab, onTab, messages, tokens, onOpenCase, onOpenChat, onNewChat,
}: Props) {
  const { user, role, setRole, model, setModel, language, setLanguage, logout } = useSession();
  const { cases, chats, refreshChats } = useWorkspace();
  const t = useT();

  const removeChat = async (threadId: string) => {
    await deleteChat(threadId).catch(() => undefined);
    refreshChats();
  };
  const isAdmin = user?.role === "admin";
  const displayName = user?.display_name ?? "";

  const pricing = config.pricing[model] ?? [0, 0];
  const cost = (tokens.input / 1_000_000) * pricing[0] + (tokens.output / 1_000_000) * pricing[1];

  return (
    <aside className="flex h-full w-72 flex-col gap-4 overflow-y-auto border-r border-outline-variant bg-surface-container-lowest px-5 py-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold text-primary">
          <span>⚖️</span> {t("app.title")}
        </h1>
        <p className="mt-1 text-xs text-on-surface-variant">{t("sidebar.subtitle")}</p>
      </div>

      <button
        onClick={onNewChat}
        className="flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 font-medium text-on-primary shadow-card hover:opacity-90"
      >
        <Icon name="add" className="text-base" /> {t("sidebar.newChat")}
      </button>

      <nav className="space-y-1">
        {TABS.filter((tab) => !tab.adminOnly || isAdmin).map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTab(tab.id)}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm ${
              activeTab === tab.id
                ? "bg-surface-container-high font-medium text-primary"
                : "text-on-surface-variant hover:bg-surface-container-low"
            }`}
          >
            <Icon name={tab.icon} className="text-base" /> {t(`nav.${tab.id}`)}
          </button>
        ))}
      </nav>

      <hr className="border-outline-variant" />

      <div className="space-y-2 text-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-on-primary">
            {displayName.slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{displayName}</p>
            <p className="truncate text-xs text-on-surface-variant">
              {isAdmin ? t("sidebar.roleAdmin") : t("sidebar.roleUser")}
            </p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-outline-variant px-3 py-2 text-sm font-medium text-on-surface-variant hover:bg-surface-container-low hover:text-primary"
        >
          <Icon name="logout" className="text-base" /> {t("sidebar.logout")}
        </button>
      </div>

      {/* Language toggle — switches both the UI shell and the assistant's answers. */}
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{t("sidebar.language")}</span>
        <div className="flex overflow-hidden rounded-lg border border-outline-variant">
          {["de", "en"].map((lng) => (
            <button
              key={lng}
              onClick={() => setLanguage(lng)}
              className={`px-3 py-1 text-xs font-medium ${
                language === lng
                  ? "bg-primary text-on-primary"
                  : "text-on-surface-variant hover:bg-surface-container-low"
              }`}
            >
              {lng.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <label className="block text-sm">
        <span className="font-medium">{t("sidebar.perspective")}</span>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
          className="mt-1 w-full rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
        >
          {config.roles.map((r) => (
            <option key={r.key} value={r.key}>
              {r.label}
            </option>
          ))}
        </select>
      </label>

      <label className="block text-sm">
        <span className="font-medium">{t("sidebar.model")}</span>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="mt-1 w-full rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
        >
          {config.models.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      <hr className="border-outline-variant" />
      <MietfallPanel />

      {cases.length > 0 && (
        <>
          <hr className="border-outline-variant" />
          <div className="space-y-2 text-sm">
            <p className="font-semibold text-on-surface">{t("sidebar.akten")}</p>
            <ul className="space-y-1">
              {cases.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => onOpenCase(c.id)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-on-surface-variant hover:bg-surface-container-low"
                  >
                    <span
                      title={
                        c.next_due
                          ? isOverdue(c.next_due)
                            ? t("sidebar.deadlineOverdue")
                            : t("sidebar.deadlineOpen")
                          : t("sidebar.deadlineNone")
                      }
                      className={`h-2 w-2 shrink-0 rounded-full ${
                        c.next_due
                          ? isOverdue(c.next_due)
                            ? "bg-error"
                            : "bg-warning"
                          : "bg-outline-variant"
                      }`}
                    />
                    <span className="min-w-0 flex-1 truncate">{c.title}</span>
                    {c.open_deadlines > 0 && (
                      <span className="shrink-0 text-xs text-on-surface-variant">
                        {c.open_deadlines}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {chats.length > 0 && (
        <>
          <hr className="border-outline-variant" />
          <div className="space-y-2 text-sm">
            <p className="font-semibold text-on-surface">{t("sidebar.verlauf")}</p>
            <ul className="space-y-0.5">
              {chats.slice(0, 12).map((c) => (
                <li key={c.thread_id} className="group flex items-center gap-1">
                  <button
                    onClick={() => onOpenChat(c.thread_id)}
                    className="min-w-0 flex-1 truncate rounded-lg px-2 py-1.5 text-left text-on-surface-variant hover:bg-surface-container-low"
                    title={c.title}
                  >
                    {c.title}
                  </button>
                  <button
                    onClick={() => removeChat(c.thread_id)}
                    title={t("sidebar.deleteChat")}
                    className="shrink-0 text-on-surface-variant opacity-0 hover:text-error group-hover:opacity-100"
                  >
                    <Icon name="close" className="text-sm" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {messages.length > 0 && (
        <>
          <hr className="border-outline-variant" />
          <ExportMenu messages={messages} />
        </>
      )}

      {(tokens.input > 0 || tokens.output > 0) && (
        <>
          <hr className="border-outline-variant" />
          <div className="text-sm">
            <p className="mb-1 font-semibold">{t("sidebar.tokenUsage")}</p>
            <p className="text-on-surface-variant">
              {t("sidebar.tokenInput")}: {tokens.input.toLocaleString("de-DE")} · {t("sidebar.tokenOutput")}:{" "}
              {tokens.output.toLocaleString("de-DE")}
            </p>
            <p className="text-xs text-on-surface-variant">{t("sidebar.estCost")}: ${cost.toFixed(5)}</p>
          </div>
        </>
      )}

      <div className="mt-auto border-t border-outline-variant pt-3 text-xs text-on-surface-variant">
        <Icon name="gavel" className="mr-1 align-middle text-sm" /> {t("sidebar.disclaimer")}
      </div>
    </aside>
  );
}
