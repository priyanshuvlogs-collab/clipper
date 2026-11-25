"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LifeBuoy, Loader2, RotateCcw, Send, X } from "lucide-react";
import { api, streamHelpChat, type ChatMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const STORAGE_KEY = "proclipper.help-chat";

const SUGGESTIONS: { match: (path: string) => boolean; questions: string[] }[] = [
  {
    match: (p) => p.startsWith("/jobs/"),
    questions: ["How do I add B-roll to this clip?", "Why did a layer fail?", "How do I add a voiceover?"],
  },
  {
    match: (p) => p.startsWith("/settings"),
    questions: ["Which key do I need for what?", "Where do I get a Grok API key?", "How is spend calculated?"],
  },
  {
    match: () => true,
    questions: ["How do I make my first clip?", "Which API keys do I need?", "What can AI Studio do?"],
  },
];

function loadSaved(): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as ChatMessage[]) : [];
    return Array.isArray(parsed) ? parsed.slice(-40) : [];
  } catch {
    return [];
  }
}

export function HelpChat() {
  const pathname = usePathname() ?? "/";
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [configured, setConfigured] = useState<boolean | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => setMessages(loadSaved()), []);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-40)));
    } catch {
      /* storage unavailable — chat still works for this page view */
    }
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    api
      .aiStatus()
      .then((s) => setConfigured(s.anthropic.configured))
      .catch(() => setConfigured(null));
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || sending) return;
    setError("");
    setInput("");
    const history: ChatMessage[] = [...messages, { role: "user", content: question }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setSending(true);
    abort.current = new AbortController();
    const jobId = pathname.match(/^\/jobs\/([0-9a-f]{32})/)?.[1];
    try {
      await streamHelpChat(
        { messages: history, page: pathname, job_id: jobId },
        (chunk) =>
          setMessages((m) => {
            const last = m[m.length - 1];
            return [...m.slice(0, -1), { ...last, content: last.content + chunk }];
          }),
        abort.current.signal,
      );
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        setError(e instanceof Error ? e.message : "Something went wrong");
      }
      // Drop an empty assistant bubble so the question can simply be re-sent.
      setMessages((m) => (m[m.length - 1]?.content ? m : m.slice(0, -1)));
    } finally {
      setSending(false);
    }
  };

  const suggestions = SUGGESTIONS.find((s) => s.match(pathname))?.questions ?? [];

  return (
    <>
      {open && (
        <section
          role="dialog"
          aria-label="Help chat"
          className="fixed inset-x-3 bottom-20 z-50 flex max-h-[min(34rem,calc(100dvh-7rem))] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/60 sm:inset-x-auto sm:right-5 sm:w-[24rem]"
        >
          <header className="flex items-center justify-between border-b border-border bg-surface-2 px-4 py-3">
            <div>
              <p className="text-sm font-bold">Help</p>
              <p className="text-[11px] text-muted">Ask anything about using Pro Clipper</p>
            </div>
            <div className="flex items-center gap-1">
              {messages.length > 0 && (
                <Button
                  variant="ghost"
                  size="icon"
                  title="Start a new chat"
                  onClick={() => {
                    abort.current?.abort();
                    setMessages([]);
                    setError("");
                  }}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                </Button>
              )}
              <Button variant="ghost" size="icon" title="Close" onClick={() => setOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </header>

          <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-4 py-3" aria-live="polite">
            {configured === false ? (
              <div className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-[13px] text-warning">
                The help chat runs on Claude and needs an Anthropic API key.{" "}
                <Link href="/settings" className="font-semibold underline" onClick={() => setOpen(false)}>
                  Add it in AI settings
                </Link>
                .
              </div>
            ) : (
              messages.length === 0 && (
                <div className="space-y-2">
                  <p className="text-[13px] text-muted">
                    Hi! I know how this app works and can see what is on your screen. Try one of these:
                  </p>
                  {suggestions.map((q) => (
                    <button
                      key={q}
                      onClick={() => send(q)}
                      className="block w-full cursor-pointer rounded-lg border border-border bg-surface-2 px-3 py-2 text-left text-[13px] transition hover:border-primary/60"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )
            )}

            {messages.map((m, i) => (
              <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[88%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed",
                    m.role === "user" ? "bg-primary text-white" : "border border-border bg-surface-2 text-foreground",
                  )}
                >
                  {m.content || <Loader2 className="h-3.5 w-3.5 animate-spin text-muted" aria-label="Thinking" />}
                </div>
              </div>
            ))}

            {error && (
              <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>
            )}
          </div>

          <form
            className="flex items-end gap-2 border-t border-border p-3"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              maxLength={4000}
              disabled={configured === false}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Type your question…"
              aria-label="Your question"
              className="max-h-28 min-h-9.5 flex-1 resize-none rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-foreground placeholder:text-muted/70 focus:border-primary/60 focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50"
            />
            <Button type="submit" size="icon" className="h-9.5 w-9.5" disabled={sending || !input.trim()} title="Send">
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </form>
        </section>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="fixed bottom-5 right-5 z-50 flex h-12 cursor-pointer items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-white shadow-xl shadow-primary/30 transition hover:bg-primary-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        {open ? <X className="h-5 w-5" /> : <LifeBuoy className="h-5 w-5" />}
        {open ? "Close" : "Help"}
      </button>
    </>
  );
}
