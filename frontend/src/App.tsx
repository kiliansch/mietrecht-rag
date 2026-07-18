import { useEffect, useState } from "react";
import { getChatMessages, getConfig } from "./api/client";
import type { AppConfig } from "./api/types";
import { AdminUsersView } from "./components/AdminUsersView";
import { CaseDetailView } from "./components/CaseDetailView";
import { CaseListView } from "./components/CaseListView";
import { ChatView } from "./components/ChatView";
import { EvalView } from "./components/EvalView";
import { Icon } from "./components/Icon";
import { LoginView } from "./components/LoginView";
import { Sidebar, type Tab } from "./components/Sidebar";
import { useSession } from "./state/session";
import { useWorkspace } from "./state/workspace";
import { useChat } from "./state/useChat";
import { useT } from "./i18n";

export default function App() {
  const { user, newThread, setThread } = useSession();
  const { refreshProfile, refreshChats } = useWorkspace();
  const t = useT();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const chat = useChat();

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch((e) => setConfigError(e instanceof Error ? e.message : String(e)));
  }, []);

  // Reset to a safe tab when the user changes (e.g. admin logs out, user logs in).
  useEffect(() => {
    if (user?.role !== "admin" && (tab === "eval" || tab === "users")) setTab("chat");
  }, [user, tab]);

  if (configError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-center">
        <div>
          <p className="text-lg font-semibold text-error">{t("app.backendDown")}</p>
          <p className="mt-2 text-on-surface-variant">{configError}</p>
          <p className="mt-2 text-sm text-on-surface-variant">
            {t("app.backendHint")} <code>uv run python main.py serve</code>
          </p>
        </div>
      </div>
    );
  }

  if (!config) {
    return <div className="flex min-h-screen items-center justify-center text-on-surface-variant">{t("app.loading")}</div>;
  }

  if (!user) {
    return <LoginView config={config} />;
  }

  const onSend = (text: string) => {
    // A chat turn may update tenancy facts (via calculators) → refresh the panel,
    // and it indexes/updates the thread in the "Verlauf" list.
    chat.send(text).then(() => {
      refreshProfile();
      refreshChats();
    });
  };

  const onNewChat = () => {
    chat.reset();
    newThread(); // start a fresh conversation so it's a distinct saved thread
    setTab("chat");
    setDrawerOpen(false);
  };

  const onOpenCase = (caseId: string) => {
    setSelectedCaseId(caseId);
    setTab("cases");
    setDrawerOpen(false);
  };

  const onOpenChat = (threadId: string) => {
    setThread(threadId);
    setTab("chat");
    setDrawerOpen(false);
    getChatMessages(threadId)
      .then((msgs) => chat.load(msgs.map((m) => ({ ...m, feedback: null }))))
      .catch(() => chat.reset());
  };

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar: drawer on mobile, fixed on desktop. */}
      <div
        className={`fixed inset-0 z-20 bg-black/30 md:hidden ${drawerOpen ? "block" : "hidden"}`}
        onClick={() => setDrawerOpen(false)}
      />
      <div
        className={`fixed inset-y-0 left-0 z-30 transition-transform md:static md:translate-x-0 ${
          drawerOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar
          config={config}
          activeTab={tab}
          onTab={(t) => {
            setTab(t);
            setDrawerOpen(false);
          }}
          messages={chat.messages}
          tokens={chat.tokens}
          onOpenCase={onOpenCase}
          onOpenChat={onOpenChat}
          onNewChat={onNewChat}
        />
      </div>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-outline-variant bg-surface-container-lowest px-4 py-2 md:hidden">
          <button onClick={() => setDrawerOpen(true)} aria-label={t("app.menu")}>
            <Icon name="menu" />
          </button>
          <span className="font-semibold text-primary">⚖️ {t("app.title")}</span>
        </header>

        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === "chat" && (
            <ChatView
              messages={chat.messages}
              loading={chat.loading}
              onSend={onSend}
              onRate={chat.setFeedback}
              onApproval={chat.respondApproval}
            />
          )}
          {tab === "cases" &&
            (selectedCaseId ? (
              <CaseDetailView
                key={selectedCaseId}
                caseId={selectedCaseId}
                onBack={() => setSelectedCaseId(null)}
              />
            ) : (
              <div className="h-full overflow-y-auto">
                <CaseListView onOpen={setSelectedCaseId} />
              </div>
            ))}
          {tab === "eval" && user.role === "admin" && (
            <div className="h-full overflow-y-auto">
              <EvalView config={config} />
            </div>
          )}
          {tab === "users" && user.role === "admin" && (
            <div className="h-full overflow-y-auto">
              <AdminUsersView />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
