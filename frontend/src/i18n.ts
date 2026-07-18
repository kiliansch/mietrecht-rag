import { useSession } from "./state/session";

// Bilingual UI strings for the whole shell. The assistant's *answers* are localised
// server-side via the system prompt; this dictionary localises everything the app
// itself renders. Missing keys fall back to the German string, then the key.
//
// `t(key, vars?)` interpolates `{name}` placeholders. For plurals, store `.one`/`.other`
// keys and pick with `t(n === 1 ? "x.one" : "x.other", { n })`.
type Dict = Record<string, string>;

const DE: Dict = {
  // App shell
  "app.title": "Mietrecht-Assistent",
  "app.backendDown": "Backend nicht erreichbar",
  "app.backendHint": "Läuft der API-Server?",
  "app.loading": "Lädt …",
  "app.menu": "Menü",

  // Navigation
  "nav.chat": "Chat",
  "nav.cases": "Akten",
  "nav.eval": "Evaluation",
  "nav.users": "Benutzer",

  // Sidebar
  "sidebar.newChat": "Neuer Chat",
  "sidebar.subtitle": "Juristische KI-Analyse",
  "sidebar.perspective": "Meine Perspektive",
  "sidebar.model": "Modell-Einstellungen",
  "sidebar.language": "Sprache",
  "sidebar.logout": "Abmelden",
  "sidebar.roleAdmin": "Administrator",
  "sidebar.roleUser": "Benutzer",
  "sidebar.mietfall": "📁 Mein Mietfall",
  "sidebar.akten": "🗂️ Meine Akten",
  "sidebar.verlauf": "🕑 Verlauf",
  "sidebar.disclaimer": "Kein Ersatz für anwaltliche Beratung.",
  "sidebar.deleteChat": "Unterhaltung löschen",
  "sidebar.deadlineOverdue": "Überfällige Frist",
  "sidebar.deadlineOpen": "Offene Frist",
  "sidebar.deadlineNone": "Keine offenen Fristen",
  "sidebar.tokenUsage": "📊 Token-Nutzung",
  "sidebar.tokenInput": "Eingabe",
  "sidebar.tokenOutput": "Ausgabe",
  "sidebar.estCost": "Geschätzte Kosten",

  // Chat
  "chat.placeholder": "Stellen Sie Ihre Mietrechtsfrage …",
  "chat.welcome": "Wie kann ich Ihnen helfen?",
  "chat.welcomeSub":
    "Stellen Sie eine Frage zum deutschen Mietrecht — mit Quellenbelegen aus BGB, BetrKV, WoGG und Rechtsprechung.",
  "chat.send": "Senden",
  "chat.disclaimer": "KI-generierte Antworten ersetzen keine anwaltliche Beratung.",
  "chat.aiName": "Mietrecht-KI",
  "chat.analysing": "Analysiere Ihre Frage …",
  "chat.sources": "Quellen & Belege",
  "chat.example1": "Wie hoch darf meine Mietkaution maximal sein?",
  "chat.example2": "Ist eine Kündigung wegen Eigenbedarf immer rechtens?",
  "chat.example3": "Wer zahlt die Schönheitsreparaturen am Ende des Mietverhältnisses?",

  // Tool call panel
  "tool.used": "Tool verwendet",

  // Groundedness badge
  "badge.none": "Keine belegende Quelle gefunden.",
  "badge.groundedPrefix": "Belegt durch",
  "badge.statute.one": "Gesetzesstelle",
  "badge.statute.other": "Gesetzesstellen",
  "badge.ruling.one": "Urteil",
  "badge.ruling.other": "Urteile",

  // Sources
  "source.statutes": "📖 Gesetzestext",
  "source.case_law": "⚖️ Rechtsprechung",
  "source.viewFull": "Volltext der Quelle anzeigen",
  "source.openExternal": "Bei Open Legal Data öffnen",
  "source.close": "Schließen",
  "source.loading": "Lädt …",

  // Feedback buttons
  "feedback.ratedHelpful": "👍 Bewertet: hilfreich",
  "feedback.ratedNot": "👎 Bewertet: nicht hilfreich",
  "feedback.helpful": "Hilfreich",
  "feedback.notHelpful": "Nicht hilfreich",
  "feedback.commentPlaceholder": "Was hat nicht gepasst? (optional)",
  "feedback.submit": "Feedback absenden",

  // Approval card (HITL)
  "approval.createDeadline": "Vorschlag: Frist anlegen",
  "approval.saveDraft": "Vorschlag: Entwurf speichern",
  "approval.generic": "Vorschlag: {action}",
  "approval.dueOn": "Fällig am {date}",
  "approval.confirm": "Bestätigen",
  "approval.reject": "Ablehnen",

  // Mein Mietfall — fact labels + values
  "fact.monthly_net_rent": "Nettokaltmiete",
  "fact.current_rent": "Aktuelle Miete",
  "fact.local_comparable_rent": "Ortsübliche Vergleichsmiete",
  "fact.floor_area_sqm": "Wohnfläche",
  "fact.built_after_oct_2014": "Neubau (nach Okt. 2014)",
  "fact.comprehensively_modernised": "Umfassend modernisiert",
  "fact.tenancy_years": "Mietdauer",
  "fact.tenancy_type": "Mietvertragstyp",
  "fact.payment_interval": "Zahlungsintervall",
  "mietfall.yes": "Ja",
  "mietfall.no": "Nein",
  "mietfall.fromContract": "aus Vertrag",
  "mietfall.years": "Jahre",
  "mietfall.empty":
    "Noch keine Angaben. Sie füllen sich, sobald Sie die Rechner nutzen oder einen Vertrag prüfen lassen.",

  // Cases list
  "cases.title": "Meine Akten",
  "cases.subtitle":
    "Jede Akte bündelt einen Mietrechts-Fall: eigener Chat-Verlauf, Vertrag, Schreiben und Fristen.",
  "cases.newPlaceholder": "z. B. Nebenkostenabrechnung 2025",
  "cases.new": "Neue Akte",
  "cases.empty": "Noch keine Akten. Legen Sie oben Ihre erste Akte an.",
  "cases.createdOn": "Angelegt am {date}",
  "cases.doc.one": "Dokument",
  "cases.doc.other": "Dokumente",
  "cases.deleteConfirm": "Akte „{title}“ mit allen Dokumenten und Fristen löschen?",
  "cases.deleteTitle": "Akte löschen",
  "cases.overdue": "Überfällig: ",
  "cases.nextDeadline": "Nächste Frist: ",
  "cases.noDeadlines": "Keine offenen Fristen",
  "cases.openDeadlines.one": "{n} offene Frist",
  "cases.openDeadlines.other": "{n} offene Fristen",

  // Case detail
  "caseDetail.back": "Zurück",
  "caseDetail.backToCases": "Zurück zu den Akten",
  "caseDetail.subtitle": "Akte · angelegt am {date}",
  "caseDetail.analyseRequest": "📄 Bitte analysiere „{title}“ aus der Akte.",

  // Deadlines panel
  "deadlines.title": "⏰ Fristen",
  "deadlines.overdueBadge": "{n} überfällig",
  "deadlines.add": "+ Frist",
  "deadlines.cancel": "Abbrechen",
  "deadlines.titlePlaceholder": "z. B. Widerspruch einlegen",
  "deadlines.create": "Anlegen",
  "deadlines.empty": "Keine Fristen. Der Assistent schlägt Fristen aus analysierten Schreiben vor.",
  "deadlines.reopen": "Wieder öffnen",
  "deadlines.markDone": "Als erledigt markieren",
  "deadlines.overduePrefix": "Überfällig · ",
  "deadlines.byAssistant": " · vom Assistenten",
  "deadlines.delete": "Frist löschen",

  // Documents panel
  "docs.title": "📎 Dokumente",
  "docs.letter": "Schreiben",
  "docs.contract": "Vertrag",
  "docs.draft": "Entwurf",
  "docs.reading": "Lese Dokument …",
  "docs.factsImported.one": "{n} Angabe aus dem Vertrag in „Mein Mietfall“ übernommen.",
  "docs.factsImported.other": "{n} Angaben aus dem Vertrag in „Mein Mietfall“ übernommen.",
  "docs.noFactsRecognised":
    "Keine Angaben automatisch erkannt — Sie können sie über die Rechner ergänzen.",
  "docs.empty":
    "Laden Sie ein Schreiben (z. B. Kündigung, Nebenkostenabrechnung) oder Ihren Mietvertrag hoch.",
  "docs.analysedSuffix": " · analysiert",
  "docs.analyse": "Analysieren",
  "docs.analyseTitle": "Im Chat analysieren (Zusammenfassung, Rechtslage, Fristen)",
  "docs.review": "Prüfen",
  "docs.reviewing": "Prüfe …",
  "docs.reviewTitle": "Klauseln auf Wirksamkeit prüfen",
  "docs.delete": "Dokument löschen",
  "docs.deleteConfirm": "Dokument „{title}“ löschen?",
  "docs.clauseProgress": "Klausel {i}/{n}: {heading}",
  "docs.checkingClauses": "Prüfe Klauseln …",
  "docs.analysisLabel": "Analyse",
  "docs.clauseCheck": "Klauselprüfung",
  "docs.documentText": "Dokumenttext",
  "docs.exportPdf": "Als PDF exportieren",
  "docs.reasoning": "Begründung:",
  "docs.sources": "📄 Quellen",

  // Verdicts (contract clause review)
  "verdict.wirksam": "Wirksam",
  "verdict.bedenklich": "Bedenklich",
  "verdict.unwirksam": "Unwirksam",

  // Export menu
  "export.title": "💾 Export",
  "export.action": "Gespräch exportieren ({fmt})",
  "export.pdfTitle": "Mietrecht-Assistent – Gesprächsprotokoll",
  "export.pdfUser": "Nutzer",
  "export.pdfAssistant": "Assistent",

  // Admin — users
  "admin.title": "Benutzerverwaltung",
  "admin.subtitle": "Konten anlegen und deaktivieren. Eine Selbstregistrierung gibt es nicht.",
  "admin.userCreated": "Benutzer „{name}“ angelegt.",
  "admin.newAccount": "Neues Konto",
  "admin.username": "Benutzername",
  "admin.usernamePlaceholder": "z. B. anna",
  "admin.displayName": "Anzeigename",
  "admin.displayNamePlaceholder": "z. B. Anna Muster",
  "admin.password": "Passwort (min. 8 Zeichen)",
  "admin.role": "Rolle",
  "admin.roleUser": "Benutzer",
  "admin.roleAdmin": "Administrator",
  "admin.creating": "Anlegen …",
  "admin.createAccount": "Konto anlegen",
  "admin.colUser": "Benutzer",
  "admin.colRole": "Rolle",
  "admin.colStatus": "Status",
  "admin.colAction": "Aktion",
  "admin.active": "aktiv",
  "admin.inactive": "deaktiviert",
  "admin.deactivate": "Deaktivieren",
  "admin.activate": "Aktivieren",
  "admin.noUsers": "Keine Benutzer gefunden.",

  // Eval
  "eval.title": "RAGAs Evaluation",
  "eval.subtitle": "System-Metriken und Analyse-Ergebnisse der KI-Modelle.",
  "eval.start": "Evaluation starten",
  "eval.running": "Evaluation läuft … kann mehrere Minuten dauern.",
  "eval.error": "Fehler bei der Evaluation. Bitte erneut versuchen.",
  "eval.agentTitle": "🧮 Agent (End-to-End)",
  "eval.retrievalTitle": "🗄️ Retrieval — {collection}",
  "eval.naNote":
    "„N/A“ bedeutet, dass diese Metrik für die aktuelle Abfrageart nicht evaluiert wurde oder nicht genügend Daten vorliegen.",
  "eval.colMetric": "Metrik",
  "eval.colScore": "Score",
  "eval.colThreshold": "Schwelle",
  "eval.colStatus": "Status",

  // Login
  "login.subtitle": "Bitte melden Sie sich mit Ihrem Konto an.",
  "login.username": "Benutzername",
  "login.password": "Passwort",
  "login.submit": "Anmelden",
  "login.busy": "Anmelden …",
  "login.noAccount": "Kein Konto? Konten werden von der Administration vergeben.",
};

const EN: Dict = {
  // App shell
  "app.title": "Rental-Law Assistant",
  "app.backendDown": "Backend unreachable",
  "app.backendHint": "Is the API server running?",
  "app.loading": "Loading …",
  "app.menu": "Menu",

  // Navigation
  "nav.chat": "Chat",
  "nav.cases": "Cases",
  "nav.eval": "Evaluation",
  "nav.users": "Users",

  // Sidebar
  "sidebar.newChat": "New chat",
  "sidebar.subtitle": "Legal AI analysis",
  "sidebar.perspective": "My perspective",
  "sidebar.model": "Model settings",
  "sidebar.language": "Language",
  "sidebar.logout": "Sign out",
  "sidebar.roleAdmin": "Administrator",
  "sidebar.roleUser": "User",
  "sidebar.mietfall": "📁 My tenancy",
  "sidebar.akten": "🗂️ My cases",
  "sidebar.verlauf": "🕑 History",
  "sidebar.disclaimer": "Not a substitute for legal advice.",
  "sidebar.deleteChat": "Delete conversation",
  "sidebar.deadlineOverdue": "Overdue deadline",
  "sidebar.deadlineOpen": "Open deadline",
  "sidebar.deadlineNone": "No open deadlines",
  "sidebar.tokenUsage": "📊 Token usage",
  "sidebar.tokenInput": "Input",
  "sidebar.tokenOutput": "Output",
  "sidebar.estCost": "Estimated cost",

  // Chat
  "chat.placeholder": "Ask your German rental-law question …",
  "chat.welcome": "How can I help you?",
  "chat.welcomeSub":
    "Ask a question about German rental law — answered with citations from the BGB, BetrKV, WoGG and case law.",
  "chat.send": "Send",
  "chat.disclaimer": "AI-generated answers are no substitute for legal advice.",
  "chat.aiName": "Rental-Law AI",
  "chat.analysing": "Analysing your question …",
  "chat.sources": "Sources & citations",
  "chat.example1": "What is the maximum my security deposit may be?",
  "chat.example2": "Is a termination for the landlord’s own use always lawful?",
  "chat.example3": "Who pays for cosmetic repairs at the end of the tenancy?",

  // Tool call panel
  "tool.used": "Tool used",

  // Groundedness badge
  "badge.none": "No supporting source found.",
  "badge.groundedPrefix": "Backed by",
  "badge.statute.one": "statute",
  "badge.statute.other": "statutes",
  "badge.ruling.one": "ruling",
  "badge.ruling.other": "rulings",

  // Sources
  "source.statutes": "📖 Statute",
  "source.case_law": "⚖️ Case law",
  "source.viewFull": "Show the full source text",
  "source.openExternal": "Open at Open Legal Data",
  "source.close": "Close",
  "source.loading": "Loading …",

  // Feedback buttons
  "feedback.ratedHelpful": "👍 Rated: helpful",
  "feedback.ratedNot": "👎 Rated: not helpful",
  "feedback.helpful": "Helpful",
  "feedback.notHelpful": "Not helpful",
  "feedback.commentPlaceholder": "What went wrong? (optional)",
  "feedback.submit": "Send feedback",

  // Approval card (HITL)
  "approval.createDeadline": "Proposal: create deadline",
  "approval.saveDraft": "Proposal: save draft",
  "approval.generic": "Proposal: {action}",
  "approval.dueOn": "Due on {date}",
  "approval.confirm": "Confirm",
  "approval.reject": "Reject",

  // Mein Mietfall — fact labels + values
  "fact.monthly_net_rent": "Net cold rent",
  "fact.current_rent": "Current rent",
  "fact.local_comparable_rent": "Local comparable rent",
  "fact.floor_area_sqm": "Floor area",
  "fact.built_after_oct_2014": "New build (after Oct 2014)",
  "fact.comprehensively_modernised": "Comprehensively modernised",
  "fact.tenancy_years": "Tenancy duration",
  "fact.tenancy_type": "Tenancy type",
  "fact.payment_interval": "Payment interval",
  "mietfall.yes": "Yes",
  "mietfall.no": "No",
  "mietfall.fromContract": "from contract",
  "mietfall.years": "years",
  "mietfall.empty":
    "No details yet. They fill in as you use the calculators or have a contract reviewed.",

  // Cases list
  "cases.title": "My cases",
  "cases.subtitle":
    "Each case bundles one rental-law matter: its own chat history, contract, letters and deadlines.",
  "cases.newPlaceholder": "e.g. Service-charge statement 2025",
  "cases.new": "New case",
  "cases.empty": "No cases yet. Create your first case above.",
  "cases.createdOn": "Created on {date}",
  "cases.doc.one": "document",
  "cases.doc.other": "documents",
  "cases.deleteConfirm": "Delete case “{title}” with all documents and deadlines?",
  "cases.deleteTitle": "Delete case",
  "cases.overdue": "Overdue: ",
  "cases.nextDeadline": "Next deadline: ",
  "cases.noDeadlines": "No open deadlines",
  "cases.openDeadlines.one": "{n} open deadline",
  "cases.openDeadlines.other": "{n} open deadlines",

  // Case detail
  "caseDetail.back": "Back",
  "caseDetail.backToCases": "Back to cases",
  "caseDetail.subtitle": "Case · created on {date}",
  "caseDetail.analyseRequest": "📄 Please analyse “{title}” from this case.",

  // Deadlines panel
  "deadlines.title": "⏰ Deadlines",
  "deadlines.overdueBadge": "{n} overdue",
  "deadlines.add": "+ Deadline",
  "deadlines.cancel": "Cancel",
  "deadlines.titlePlaceholder": "e.g. File an objection",
  "deadlines.create": "Create",
  "deadlines.empty": "No deadlines. The assistant proposes deadlines from analysed letters.",
  "deadlines.reopen": "Reopen",
  "deadlines.markDone": "Mark as done",
  "deadlines.overduePrefix": "Overdue · ",
  "deadlines.byAssistant": " · by the assistant",
  "deadlines.delete": "Delete deadline",

  // Documents panel
  "docs.title": "📎 Documents",
  "docs.letter": "Letter",
  "docs.contract": "Contract",
  "docs.draft": "Draft",
  "docs.reading": "Reading document …",
  "docs.factsImported.one": "Imported {n} detail from the contract into “My tenancy”.",
  "docs.factsImported.other": "Imported {n} details from the contract into “My tenancy”.",
  "docs.noFactsRecognised":
    "No details recognised automatically — you can add them via the calculators.",
  "docs.empty":
    "Upload a letter (e.g. termination, service-charge statement) or your rental contract.",
  "docs.analysedSuffix": " · analysed",
  "docs.analyse": "Analyse",
  "docs.analyseTitle": "Analyse in chat (summary, legal position, deadlines)",
  "docs.review": "Review",
  "docs.reviewing": "Reviewing …",
  "docs.reviewTitle": "Check clauses for validity",
  "docs.delete": "Delete document",
  "docs.deleteConfirm": "Delete document “{title}”?",
  "docs.clauseProgress": "Clause {i}/{n}: {heading}",
  "docs.checkingClauses": "Checking clauses …",
  "docs.analysisLabel": "Analysis",
  "docs.clauseCheck": "Clause review",
  "docs.documentText": "Document text",
  "docs.exportPdf": "Export as PDF",
  "docs.reasoning": "Reasoning:",
  "docs.sources": "📄 Sources",

  // Verdicts (contract clause review)
  "verdict.wirksam": "Valid",
  "verdict.bedenklich": "Questionable",
  "verdict.unwirksam": "Invalid",

  // Export menu
  "export.title": "💾 Export",
  "export.action": "Export conversation ({fmt})",
  "export.pdfTitle": "Rental-Law Assistant – Conversation transcript",
  "export.pdfUser": "User",
  "export.pdfAssistant": "Assistant",

  // Admin — users
  "admin.title": "User management",
  "admin.subtitle": "Create and deactivate accounts. There is no self-registration.",
  "admin.userCreated": "User “{name}” created.",
  "admin.newAccount": "New account",
  "admin.username": "Username",
  "admin.usernamePlaceholder": "e.g. anna",
  "admin.displayName": "Display name",
  "admin.displayNamePlaceholder": "e.g. Jane Doe",
  "admin.password": "Password (min. 8 characters)",
  "admin.role": "Role",
  "admin.roleUser": "User",
  "admin.roleAdmin": "Administrator",
  "admin.creating": "Creating …",
  "admin.createAccount": "Create account",
  "admin.colUser": "User",
  "admin.colRole": "Role",
  "admin.colStatus": "Status",
  "admin.colAction": "Action",
  "admin.active": "active",
  "admin.inactive": "deactivated",
  "admin.deactivate": "Deactivate",
  "admin.activate": "Activate",
  "admin.noUsers": "No users found.",

  // Eval
  "eval.title": "RAGAs Evaluation",
  "eval.subtitle": "System metrics and analysis results of the AI models.",
  "eval.start": "Start evaluation",
  "eval.running": "Evaluation running … this may take several minutes.",
  "eval.error": "Evaluation failed. Please try again.",
  "eval.agentTitle": "🧮 Agent (end-to-end)",
  "eval.retrievalTitle": "🗄️ Retrieval — {collection}",
  "eval.naNote":
    "“N/A” means this metric was not evaluated for the current query type, or there is not enough data.",
  "eval.colMetric": "Metric",
  "eval.colScore": "Score",
  "eval.colThreshold": "Threshold",
  "eval.colStatus": "Status",

  // Login
  "login.subtitle": "Please sign in with your account.",
  "login.username": "Username",
  "login.password": "Password",
  "login.submit": "Sign in",
  "login.busy": "Signing in …",
  "login.noAccount": "No account? Accounts are provisioned by an administrator.",
};

const DICTS: Record<string, Dict> = { de: DE, en: EN };

export type TFunc = (key: string, vars?: Record<string, string | number>) => string;

/** Returns a `t(key, vars?)` translator bound to the current session language. */
export function useT(): TFunc {
  const { language } = useSession();
  return makeT(language);
}

/** Build a translator for an explicit language (for non-hook callers, e.g. PDF export). */
export function makeT(language: string): TFunc {
  const dict = DICTS[language] ?? DE;
  return (key, vars) => {
    const template = dict[key] ?? DE[key] ?? key;
    if (!vars) return template;
    return template.replace(/\{(\w+)\}/g, (_, name) =>
      name in vars ? String(vars[name]) : `{${name}}`,
    );
  };
}
