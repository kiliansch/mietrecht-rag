"""Case tools with human-in-the-loop approval (LangGraph `interrupt()`).

Both tools call `interrupt(...)` as their FIRST statement: `ToolNode` propagates the
interrupt, the checkpointer parks the thread, and the API surfaces an
`approval_required` SSE event. `Command(resume={interrupt_id: "approve"|"reject"})`
re-enters the tools node, where `interrupt()` returns the decision — only then does
any write happen. NEVER put a database write before the `interrupt()` call.

Outside a case (`Context.case_id is None`) the tools are inert and return an error
string, so binding them globally is safe for free chat / contract review / eval.
"""

from __future__ import annotations

from datetime import date

from langchain_core.tools import tool
from langgraph.runtime import get_runtime
from langgraph.types import interrupt

from src.agent.state import Context

_REJECTED = "Der Nutzer hat diese Aktion abgelehnt. Nicht erneut vorschlagen."
_NO_CASE = (
    "Keine Akte aktiv — dieses Werkzeug funktioniert nur im Kontext einer Akte. "
    "Bitte die Information stattdessen im Antworttext nennen."
)


@tool
def create_deadline(title: str, due_date: str, note: str = "") -> str:
    """
    Legt eine rechtliche Frist in der aktuellen Akte an. Erfordert die Bestätigung
    des Nutzers, bevor die Frist gespeichert wird.

    Verwende dieses Tool, wenn du in einem Schreiben oder Gespräch eine konkrete
    rechtliche Frist identifizierst (z. B. Widerspruchs-, Zahlungs- oder
    Kündigungsfrist). Schlage immer nur EINE Frist pro Antwortschritt vor.
    Eingabe: title (kurzer Titel), due_date (Datum im Format JJJJ-MM-TT),
    note (optionale Begründung/Quelle).
    """
    decision = interrupt(
        {"action": "create_deadline", "args": {"title": title, "due_date": due_date, "note": note}}
    )
    if decision != "approve":
        return _REJECTED

    ctx = get_runtime(Context).context
    if ctx.case_id is None:
        return _NO_CASE
    try:
        due = date.fromisoformat(due_date).isoformat()
    except ValueError:
        return f"Ungültiges Datum '{due_date}' — erwartet wird das Format JJJJ-MM-TT."

    from src.cases import store as cases_store  # local import: keep tool import-light

    cases_store.add_deadline(
        ctx.case_id, title=title, due_date=due, note=note, created_by="agent"
    )
    return f"Frist '{title}' zum {due} wurde in der Akte angelegt."


@tool
def save_draft(title: str, content: str) -> str:
    """
    Speichert ein Antwortschreiben (Entwurf) in der aktuellen Akte. Erfordert die
    Bestätigung des Nutzers, bevor der Entwurf gespeichert wird.

    Verwende dieses Tool, nachdem du auf Wunsch des Nutzers ein versandfertiges
    Schreiben formuliert hast (z. B. Widerspruch, Mängelanzeige, Antwort an den
    Vermieter). Eingabe: title (kurzer Betreff), content (vollständiger Text des
    Schreibens in Markdown, inklusive §-Referenzen aus den Suchwerkzeugen).
    """
    decision = interrupt(
        {"action": "save_draft", "args": {"title": title, "content": content}}
    )
    if decision != "approve":
        return _REJECTED

    ctx = get_runtime(Context).context
    if ctx.case_id is None:
        return _NO_CASE

    from src.cases import store as cases_store  # local import: keep tool import-light

    cases_store.add_document(ctx.case_id, kind="draft", title=title, content=content)
    return f"Entwurf '{title}' wurde in der Akte gespeichert."
