import { FormEvent, Fragment, KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AiChatResult, AiConversation, AiMessage, deleteAiConversation, getAiConversation, getAiSettings, listAiConversations, runAiChat } from "../api";
import { Icon } from "../components/Icon";
import { useAi } from "./AiContext";
import { useSelectedConnection } from "./ConnectionContext";

/** Renders the model's plain text: **bold**, and "* " or "- " lines as a bullet list. */
function renderAnswer(text: string): ReactNode {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length) {
      blocks.push(<ul key={`ul-${blocks.length}`}>{bullets.map((b, i) => <li key={i}>{boldParts(b)}</li>)}</ul>);
      bullets = [];
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[*-]\s+(.*)$/);
    if (bullet) {
      bullets.push(bullet[1]);
    } else {
      flush();
      if (line.trim()) blocks.push(<p key={`p-${blocks.length}`}>{boldParts(line)}</p>);
    }
  }
  flush();
  return blocks;
}

function boldParts(line: string): ReactNode {
  return line.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 === 1 ? <strong key={i}>{part}</strong> : <Fragment key={i}>{part}</Fragment>));
}

/** Per-browser conveniences; the conversations themselves are saved by the server. */
function remember(key: string, value?: string): string {
  try {
    if (value !== undefined) localStorage.setItem(key, value);
    return localStorage.getItem(key) ?? "";
  } catch {
    return value ?? "";
  }
}

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/** FSD §11.3 slide-out AI panel. Suggested questions come from the configured model, never a fixed list. */
function AiPanel() {
  const connectionId = useSelectedConnection();
  const navigate = useNavigate();
  const ai = useAi();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [activeModel, setActiveModel] = useState("");
  const [provider, setProvider] = useState("");
  const [privacy, setPrivacy] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<AiMessage[]>([]);
  const [full, setFull] = useState(() => remember("tarsier-ai-mode") === "full");
  const [history, setHistory] = useState<AiConversation[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);
  const conversation = useRef("");
  const rootRef = useRef<HTMLDivElement>(null);
  const [suggestions, setSuggestions] = useState<string[] | null>(null);
  const [suggestBusy, setSuggestBusy] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [suggestRetry, setSuggestRetry] = useState(0);
  // Suggestions per connection and model, so reopening the panel does not call the model again.
  const suggestCache = useRef(new Map<string, string[]>());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getAiSettings()
      .then((s) => {
        setConfigured(s.configured);
        setActiveModel(s.model || "No model selected");
        setProvider(s.provider === "external" ? "OpenRouter" : "Ollama · Local");
        setPrivacy(s.privacy_warning);
      })
      .catch(() => setConfigured(false));
  }, [ai.open]);

  useEffect(() => {
    if (ai.seed) setInput(ai.seed);
  }, [ai.seed, ai.open]);

  function refreshHistory(forConnection: string) {
    listAiConversations(forConnection).then(setHistory).catch(() => setHistory([]));
  }

  function openConversation(forConnection: string, id: string) {
    conversation.current = id;
    remember(`tarsier-chat-${forConnection}`, id);
    setMessages([]);
    setError(null);
    setHistoryOpen(false);
    getAiConversation(forConnection, id)
      .then((saved) => { if (conversation.current === id) setMessages(saved); })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load that conversation."));
  }

  function startConversation() {
    conversation.current = newId();
    if (connectionId) remember(`tarsier-chat-${connectionId}`, conversation.current);
    setMessages([]);
    setInput("");
    setError(null);
    setHistoryOpen(false);
  }

  // Reopen the last conversation of this connection, so a refresh or restart keeps the chat.
  useEffect(() => {
    setMessages([]);
    setInput("");
    setError(null);
    setHistory([]);
    if (!connectionId) return;
    const last = remember(`tarsier-chat-${connectionId}`);
    if (last) openConversation(connectionId, last);
    else conversation.current = newId();
    refreshHistory(connectionId);
    // openConversation and refreshHistory only use their arguments and state setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId]);

  // While the panel is open the page behind it can be neither scrolled, clicked nor tabbed into.
  useEffect(() => {
    const root = rootRef.current;
    if (!ai.open || !root?.parentElement) return;
    const others = Array.from(root.parentElement.children).filter((el) => el !== root && !el.hasAttribute("inert"));
    others.forEach((el) => el.setAttribute("inert", ""));
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") ai.hide(); };
    window.addEventListener("keydown", onKey);
    return () => {
      others.forEach((el) => el.removeAttribute("inert"));
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [ai.open, ai.hide]);

  // Keep the newest message in view.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  const showSuggestions = ai.open && configured === true && Boolean(connectionId) && ai.job === "explain-changes";
  const suggestKey = `${connectionId}|${activeModel}`;

  // As soon as a model is configured, ask it for starter questions about this connection.
  useEffect(() => {
    if (!showSuggestions || !connectionId) return;
    const cached = suggestCache.current.get(suggestKey);
    if (cached) {
      setSuggestions(cached);
      setSuggestError(null);
      return;
    }
    let cancelled = false;
    setSuggestBusy(true);
    setSuggestError(null);
    setSuggestions(null);
    runAiChat(connectionId, { job: "suggest-questions" })
      .then((result) => {
        if (cancelled) return;
        const questions = result.questions ?? [];
        suggestCache.current.set(suggestKey, questions);
        setSuggestions(questions);
      })
      .catch((err) => {
        if (!cancelled) setSuggestError(err instanceof Error ? err.message : "Could not load suggestions.");
      })
      .finally(() => {
        if (!cancelled) setSuggestBusy(false);
      });
    return () => { cancelled = true; };
    // suggestKey already contains connectionId and activeModel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSuggestions, suggestKey, suggestRetry]);

  if (!ai.open) return null;

  const chatStarted = messages.length > 0;

  async function submit(rawText: string) {
    if (!connectionId) { setError("Select a connection to start a conversation about your data."); return; }
    if (ai.job === "query") {
      setError("Plain-English query lives on the Statistics tab for a chosen layer.");
      return;
    }
    const text = rawText.trim();
    if (ai.job === "build-automation" && !text) {
      setError("Describe the automation you want.");
      return;
    }
    // A typed question goes to the free-question job; the quality button keeps its own job.
    const job = ai.job === "explain-changes" && text ? "ask" : ai.job;
    if (!text && job === "ask") return;
    if (text) setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    const conversationId = conversation.current;
    if (job === "ask") remember(`tarsier-chat-${connectionId}`, conversationId);
    setError(null);
    setBusy(true);
    try {
      const result: AiChatResult = await runAiChat(connectionId, {
        job,
        message: text,
        schema: ai.schema,
        name: ai.name,
        check_id: ai.checkId,
        conversation_id: job === "ask" ? conversationId : undefined,
      });
      // The reader may have switched conversation while the model was thinking.
      if (conversation.current !== conversationId) return;
      setMessages((prev) => [...prev, { role: "ai", text: result.text }]);
      refreshHistory(connectionId);
      if (result.graph && connectionId) {
        sessionStorage.setItem(`tarsier-auto-draft-${connectionId}`, JSON.stringify(result));
        ai.notifyDraft();
        ai.hide();
        navigate(`/connections/${connectionId}/automations`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the AI assistant.");
    } finally {
      setBusy(false);
    }
  }

  function send(event?: FormEvent) {
    event?.preventDefault();
    if (busy || !input.trim()) return;
    void submit(input);
  }

  function onComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  }

  function toggleFull() {
    setFull((value) => {
      remember("tarsier-ai-mode", value ? "side" : "full");
      return !value;
    });
  }

  function removeConversation(id: string) {
    if (!connectionId) return;
    deleteAiConversation(connectionId, id)
      .then(() => {
        if (conversation.current === id) startConversation();
        refreshHistory(connectionId);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not delete that conversation."));
  }

  function copy(text: string, index: number) {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(index);
      window.setTimeout(() => setCopied(null), 1500);
    }).catch(() => undefined);
  }

  const showHistory = full || historyOpen;
  const iconButton = (label: string, name: Parameters<typeof Icon>[0]["name"], onClick: () => void) => (
    <button type="button" className="assistant-icon" aria-label={label} title={label} onClick={onClick}>
      <Icon name={name} />
    </button>
  );

  return (
    <div className="assistant-root" ref={rootRef}>
    <div className="assistant-veil" aria-hidden="true" />
    <aside className={`assistant-panel${full ? " is-full" : ""}${chatStarted ? " is-chatting" : ""}`} role="dialog" aria-modal="true" aria-label="AI assistant">
      <header className="assistant-header">
        <div className="assistant-title">
          <span className="assistant-avatar"><Icon name="sparkle" size={18} /></span>
          <div>
            <h2>AI assistant</h2>
            <Link to="/settings#ai" onClick={ai.hide} className="assistant-modelline" title="Change model">
              {configured && <i aria-hidden="true" />}
              {activeModel || "Loading model…"}{provider ? ` · ${provider}` : ""}
              <Icon name="chevronDown" size={13} />
            </Link>
          </div>
        </div>
        <div className="assistant-tools">
          {iconButton("New chat", "newChat", startConversation)}
          {!full && iconButton("Past conversations", "history", () => setHistoryOpen((v) => !v))}
          {iconButton(full ? "Shrink to side panel" : "Full screen", full ? "shrink" : "expand", toggleFull)}
          {iconButton("Close assistant", "close", ai.hide)}
        </div>
      </header>

      <div className="assistant-body">
      {showHistory && (
        <nav className="assistant-history" aria-label="Past conversations">
          <p className="t-label">Past conversations</p>
          {!history.length && <p className="t-caption">Nothing saved yet.</p>}
          {history.map((item) => (
            <div key={item.id} className={`assistant-history-row${item.id === conversation.current ? " active" : ""}`}>
              <button type="button" className="assistant-history-open" onClick={() => connectionId && openConversation(connectionId, item.id)}>
                <span>{item.title}</span>
                <small>{new Date(item.updated_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</small>
              </button>
              <button type="button" className="assistant-icon small" aria-label={`Delete conversation: ${item.title}`} title="Delete" onClick={() => removeConversation(item.id)}>
                <Icon name="trash" size={15} />
              </button>
            </div>
          ))}
        </nav>
      )}
      <div className="assistant-chat">
      {configured === false && (
        <p className="assistant-notice">
          Set up AI in Settings. <Link to="/settings">Open Settings</Link>
        </p>
      )}
      {privacy && !dismissed && (
        <p className="assistant-notice">
          {privacy}{" "}
          <button type="button" className="assistant-link" onClick={() => setDismissed(true)}>Dismiss</button>
        </p>
      )}

      {configured && (
        <>
          <div className="assistant-messages" ref={scrollRef} aria-live="polite">
            {!chatStarted && (
              <div className="assistant-welcome">
                <span className="assistant-avatar large"><Icon name="sparkle" size={26} /></span>
                <h3 className="t-display-sm">A closer look at your data</h3>
                <p className="t-caption">{ai.job === "build-automation" ? "Describe what should happen and when. You will review the workflow before saving it." : ai.job === "explain-quality" ? "Understand a quality finding and the steps you can take next." : "Ask about this connection, or pick a suggestion."}</p>
                {!connectionId && <p className="t-caption">Select a connection to get started.</p>}
              </div>
            )}

            {showSuggestions && !chatStarted && (
              <section className="assistant-suggest" aria-label="Suggested questions">
                <p className="t-label">Suggested questions</p>
                {suggestBusy && (
                  <div className="assistant-suggest-loading" role="status" aria-busy="true">
                    <span className="skeleton" /><span className="skeleton" /><span className="skeleton" />
                    <span className="t-caption">The model is reading your layers…</span>
                  </div>
                )}
                {suggestError && (
                  <div className="assistant-suggest-error">
                    <p className="t-caption" role="alert">{suggestError}</p>
                    <button type="button" className="assistant-link" onClick={() => { suggestCache.current.delete(suggestKey); setSuggestRetry((n) => n + 1); }}>Try again</button>
                  </div>
                )}
                {suggestions && suggestions.length > 0 && (
                  <div className="assistant-chips">
                    {suggestions.map((question) => (
                      <button key={question} type="button" className="assistant-chip" disabled={busy} onClick={() => void submit(question)}>
                        <Icon name="sparkle" size={15} />
                        <span>{question}</span>
                      </button>
                    ))}
                  </div>
                )}
              </section>
            )}

            {messages.map((msg, i) => (
              msg.role === "user" ? (
                <div key={i} className="assistant-bubble user"><p>{msg.text}</p></div>
              ) : (
                <div key={i} className="assistant-row">
                  <span className="assistant-avatar"><Icon name="sparkle" size={15} /></span>
                  <div className="assistant-answer">
                    {renderAnswer(msg.text)}
                    <button type="button" className="assistant-icon small assistant-copy" aria-label="Copy answer" title="Copy" onClick={() => copy(msg.text, i)}>
                      <Icon name={copied === i ? "check" : "copy"} size={15} />
                    </button>
                  </div>
                </div>
              )
            ))}

            {busy && (
              <div className="assistant-row" role="status" aria-busy="true" aria-label="Thinking">
                <span className="assistant-avatar"><Icon name="sparkle" size={15} /></span>
                <span className="assistant-typing"><i /><i /><i /></span>
              </div>
            )}
          </div>

          {ai.job === "explain-quality" && ai.checkId && (
            <button type="button" className="assistant-action" onClick={() => void submit("")} disabled={busy}>
              Explain this check
            </button>
          )}

          <form className="assistant-composer" onSubmit={send}>
            <textarea
              aria-label="Message to AI assistant"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onComposerKey}
              placeholder={ai.job === "build-automation" ? "Notify me when…" : "Ask anything about this connection"}
              rows={1}
              disabled={busy}
            />
            <button type="submit" className="assistant-send" disabled={busy || !connectionId || !input.trim()} aria-label="Send message" title="Send">
              <Icon name="arrowUp" size={17} />
            </button>
          </form>
        </>
      )}
      {error && (
        <p role="alert" className="assistant-notice error">
          {error}
        </p>
      )}
      </div>
      </div>
    </aside>
    </div>
  );
}

export default AiPanel;
