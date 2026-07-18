import { useCallback, useRef, useState } from "react";
import { postChat, postResume } from "../api/client";
import { parseSSE } from "../api/sse";
import type { ChatMessage, PendingApproval, Source, ToolCall } from "../api/types";
import { useSession } from "./session";

export interface TokenTotals {
  input: number;
  output: number;
}

// De-dupe by URL (else header) so repeated chunks of the same case/§ aren't stored twice.
const dedupeSource = (sources: Source[], s: Source): Source[] =>
  sources.some((x) => (x.url || x.header) === (s.url || s.header)) ? sources : [...sources, s];

/**
 * Chat state for one conversation surface.
 * Without `caseId`: the free-chat tab on the session's ephemeral thread.
 * With `caseId`: the case's persistent server-side thread.
 */
export function useChat(caseId?: string) {
  const { role, model, language, threadId } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tokens, setTokens] = useState<TokenTotals>({ input: 0, output: 0 });
  const [loading, setLoading] = useState(false);
  // The in-flight turn's controller; aborted when a new turn starts or the
  // transcript is replaced, so a stale stream can't mutate the wrong message.
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setTokens({ input: 0, output: 0 });
  }, []);

  /** Replace the transcript with a reopened saved thread's turns. */
  const load = useCallback((loaded: ChatMessage[]) => {
    abortRef.current?.abort();
    setMessages(loaded);
    setTokens({ input: 0, output: 0 });
  }, []);

  const setFeedback = useCallback((index: number, value: 1 | -1) => {
    setMessages((prev) =>
      prev.map((m, i) => (i === index ? { ...m, feedback: value } : m)),
    );
  }, []);

  const update = useCallback((mut: (d: ChatMessage) => void) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = { ...next[next.length - 1] };
      mut(last);
      next[next.length - 1] = last;
      return next;
    });
  }, []);

  /** Consume one SSE frame into the current assistant draft (last message). */
  const applyFrame = useCallback(
    (event: string, data: Record<string, unknown>) => {
      switch (event) {
        case "tool_call":
          update((d) => {
            d.toolCalls = [
              ...(d.toolCalls ?? []),
              { id: data.id, name: data.name, args: data.args, result: null } as ToolCall,
            ];
          });
          break;
        case "tool_result":
          update((d) => {
            d.toolCalls = (d.toolCalls ?? []).map((tc) =>
              tc.id === data.id ? { ...tc, result: data.result as string } : tc,
            );
          });
          break;
        case "source":
          update((d) => {
            d.sources = dedupeSource(d.sources ?? [], data as unknown as Source);
          });
          break;
        case "usage":
          setTokens((t) => ({
            input: t.input + ((data.input_tokens as number) ?? 0),
            output: t.output + ((data.output_tokens as number) ?? 0),
          }));
          break;
        case "final":
          update((d) => {
            d.content = data.content as string;
          });
          break;
        case "error":
          update((d) => {
            d.content = `❌ ${data.message}`;
          });
          break;
        case "approval_required":
          // The agent proposed a gated action; the thread is parked server-side
          // until the user confirms or rejects (→ respondApproval).
          update((d) => {
            d.pendingApproval = data as unknown as PendingApproval;
          });
          break;
      }
    },
    [update],
  );

  /**
   * Run one streaming request into the current draft (the last message), with
   * cancellation. Aborts any previous in-flight turn first, and ignores frames /
   * errors from a turn that has since been aborted. Shared by sends, case-document
   * analyses (via `streamTurn`) and approval resumes.
   */
  const consumeStream = useCallback(
    async (makeRequest: (signal: AbortSignal) => Promise<Response>) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      try {
        const res = await makeRequest(controller.signal);
        if (controller.signal.aborted) return;
        if (!res.ok || !res.body) {
          let detail = res.statusText;
          try {
            detail = (await res.json()).detail ?? detail;
          } catch {
            /* ignore */
          }
          update((d) => {
            d.content = `❌ ${detail}`;
          });
          return;
        }
        for await (const frame of parseSSE(res.body)) {
          if (controller.signal.aborted) return;
          const data = frame.data ? JSON.parse(frame.data) : {};
          applyFrame(frame.event, data);
        }
      } catch (e) {
        if (controller.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) {
          return; // superseded/cancelled turn — leave the transcript to the new one
        }
        update((d) => {
          d.content = `❌ ${e instanceof Error ? e.message : String(e)}`;
        });
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
          setLoading(false);
        }
      }
    },
    [applyFrame, update],
  );

  /**
   * Append a user turn + assistant draft, then stream `makeRequest(signal)`'s SSE
   * response into the draft. Shared by chat sends and case document analyses.
   */
  const streamTurn = useCallback(
    async (userText: string, makeRequest: (signal: AbortSignal) => Promise<Response>) => {
      const draft: ChatMessage = { role: "assistant", content: "", toolCalls: [], sources: [], feedback: null };
      setMessages((prev) => [...prev, { role: "user", content: userText }, draft]);
      await consumeStream(makeRequest);
    },
    [consumeStream],
  );

  const send = useCallback(
    (text: string) => {
      // A new message supersedes any stale pending approval (the server treats new
      // input on an interrupted thread as replacing the parked run).
      setMessages((prev) =>
        prev.map((m) => (m.pendingApproval ? { ...m, pendingApproval: null } : m)),
      );
      return streamTurn(text, (signal) =>
        postChat(
          caseId
            ? { case_id: caseId, role, model, message: text, language }
            : { thread_id: threadId, role, model, message: text, language },
          signal,
        ),
      );
    },
    [streamTurn, caseId, role, model, language, threadId],
  );

  /** Approve/reject the pending action; the continuation streams into the same draft. */
  const respondApproval = useCallback(
    async (
      approval: PendingApproval,
      decision: "approve" | "reject",
      opts?: { documentId?: string },
    ) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.pendingApproval?.interrupt_id === approval.interrupt_id
            ? { ...m, pendingApproval: null }
            : m,
        ),
      );
      await consumeStream((signal) =>
        postResume(
          {
            ...(caseId ? { case_id: caseId } : { thread_id: threadId }),
            interrupt_id: approval.interrupt_id,
            decision,
            language,
            ...(opts?.documentId ? { document_id: opts.documentId } : {}),
          },
          signal,
        ),
      );
    },
    [consumeStream, caseId, threadId, language],
  );

  return { messages, tokens, loading, send, streamTurn, respondApproval, reset, load, setFeedback };
}
