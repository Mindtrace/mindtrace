/**
 * ChatDialogue — SSE streaming, Claude.ai style.
 *
 * Transport: fetch() + ReadableStream  (not WebSocket)
 * Each user message → one POST /mig24/camera/chat → one SSE stream → stream closes.
 *
 * SSE wire format from the server:
 *   data: {"type":"run_started",...}\n\n
 *   data: {"type":"part_delta",...}\n\n
 *   ...
 *   data: {"type":"run_finished"}\n\n
 *   (connection closes)
 *
 * Cancellation: AbortController.abort() — same as closing a WebSocket.
 * The server detects the disconnect and stops the generator.
 *
 * Event handling is identical to the WebSocket version — only the
 * transport layer changed.
 */

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import "./ChatDialogue.css";


// ── SSE stream reader ─────────────────────────────────────────────────────────
//
// fetch() gives us a ReadableStream of raw bytes.  SSE events are delimited
// by "\n\n".  A single reader.read() call may return:
//   • part of one event   → buffer until we see \n\n
//   • exactly one event   → parse immediately
//   • several events      → split and parse each
//
// We accumulate bytes in `buffer` and flush complete events as they arrive.

async function* readSSE(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Append decoded bytes to the running buffer.
      buffer += decoder.decode(value, { stream: true });

      // Split on the SSE event boundary (\n\n).
      // Everything before the last \n\n is a complete event(s).
      const parts = buffer.split("\n\n");
      buffer = parts.pop(); // keep the trailing incomplete fragment

      for (const part of parts) {
        for (const line of part.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              yield JSON.parse(line.slice(6));
            } catch {
              // Ignore malformed lines.
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ── Activity log ──────────────────────────────────────────────────────────────

function ActivityStep({ step }) {
  return (
    <div className={`activity-step ${step.done ? "done" : "active"}`}>
      <span className="activity-icon" />
      <span className="activity-label">{step.label}</span>
      {step.detail && <span className="activity-detail">{step.detail}</span>}
    </div>
  );
}

function ActivityLog({ steps, sealed }) {
  if (sealed) {
    const toolNames = steps.filter((s) => s.done && s.toolName).map((s) => s.toolName);
    const summary =
      toolNames.length > 0
        ? `Used ${toolNames.join(", ")} · ${steps.length} steps`
        : `${steps.length} steps`;
    return <div className="activity-sealed">{summary}</div>;
  }
  return (
    <div className="activity-log">
      {steps.map((step, i) => (
        <ActivityStep key={i} step={step} />
      ))}
    </div>
  );
}

// ── Message bubble ─────────────────────────────────────────────────────────────

function Message({ message }) {
  if (message.role === "system") {
    return (
      <div className="system-notice">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    );
  }
  const isUser = message.role === "user";
  return (
    <div className={`message-row ${isUser ? "user" : "assistant"}`}>
      <div className="avatar">{isUser ? "You" : "AI"}</div>
      <div className={`bubble${message.error ? " error" : ""}`}>
        {isUser
          ? message.content
          : <div className="md-content"><ReactMarkdown>{message.content}</ReactMarkdown></div>}
        {message.streaming && <span className="cursor" />}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const SERVICE_EVENT_TEXT = {
  service_started:    (name, url) => `**${name}** started${url ? ` at \`${url}\`` : ""}.`,
  service_starting:   (name)     => `**${name}** is starting…`,
  service_stopped:    (name)     => `**${name}** stopped.`,
  service_restarting: (name)     => `**${name}** is restarting…`,
  heartbeat_failed:   (name, _, error) => `**${name}** is unreachable: ${error}`,
};

export default function ChatDialogue({ apiUrl, welcomeUrl, eventsUrl = "/events", title = "Service Supervisor" }) {
  const [messages, setMessages] = useState([]);
  const sessionId = useRef(crypto.randomUUID());
  const [input, setInput]       = useState("");
  const [waiting, setWaiting]   = useState(false);
  const [activity, setActivity] = useState(null);

  // AbortController lets us cancel the in-flight fetch (= client disconnect).
  const abortRef  = useRef(null);
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  // Subscribe to service lifecycle events and inject them as system messages.
  useEffect(() => {
    const es = new EventSource(eventsUrl);
    es.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }
      if (data.type !== "notification" || data.event === "connected") return;
      const fmt = SERVICE_EVENT_TEXT[data.event];
      if (!fmt) return;
      const content = fmt(data.name, data.url, data.error);
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "system", content, streaming: false },
      ]);
    };
    return () => es.close();
  }, [eventsUrl]);

  // Fetch welcome message on mount
  useEffect(() => {
    fetch(welcomeUrl)
      .then((res) => res.json())
      .then((data) => {
        setMessages([
          {
            id: Date.now(),
            role: "assistant",
            content: data.message,
            streaming: false,
          },
        ]);
      })
      .catch((err) => {
        console.error("Failed to load welcome message:", err);
      });
  }, []);

  // Cancel any running request when the component unmounts.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // Auto-scroll to latest content.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activity]);

  // ── Event dispatcher — identical logic to the WebSocket version ─────────────

  function dispatch(ev) {
    switch (ev.type) {
      case "run_started":
        setActivity({ steps: [], sealed: false });
        break;

      case "tool_call_start":
        setActivity((prev) => ({
          steps: [
            ...(prev?.steps ?? []),
            {
              id: ev.tool_call_id,
              toolName: ev.tool_call_name,
              label: `Calling ${ev.tool_call_name}`,
              detail: "",
              done: false,
            },
          ],
          sealed: false,
        }));
        break;

      case "tool_call_end":
        setActivity((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            steps: prev.steps.map((s) =>
              s.id === ev.tool_call_id ? { ...s, done: true } : s
            ),
          };
        });
        break;

      case "tool_result":
        setActivity((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            steps: prev.steps.map((s) =>
              s.id === ev.tool_call_id ? { ...s, detail: ev.content, done: true } : s
            ),
          };
        });
        break;

      case "part_start":
        break;

      case "part_delta":
        if (ev.delta?.kind === "text") {
          // First text token → seal the activity log.
          setActivity((prev) => (prev ? { ...prev, sealed: true } : prev));
          // Append token to the streaming assistant bubble.
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + ev.delta.content_delta },
              ];
            }
            return [
              ...prev,
              { id: Date.now(), role: "assistant", content: ev.delta.content_delta, streaming: true },
            ];
          });
        }
        break;

      case "part_end":
        if (ev.part_kind === "text") {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              return [...prev.slice(0, -1), { ...last, streaming: false }];
            }
            return prev;
          });
        }
        break;

      case "agent_run_result":
        break;

      case "run_finished":
        setWaiting(false);
        setActivity(null);
        inputRef.current?.focus();
        break;

      case "run_error":
        setMessages((prev) => [
          ...prev,
          { id: Date.now(), role: "assistant", content: `Error: ${ev.message}`, streaming: false, error: true },
        ]);
        setWaiting(false);
        setActivity(null);
        inputRef.current?.focus();
        break;

      default:
        break;
    }
  }

  // ── Send a message ──────────────────────────────────────────────────────────

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || waiting) return;

    // Add user bubble immediately.
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "user", content: text, streaming: false },
    ]);
    setInput("");
    setWaiting(true);
    setActivity(null);

    // Create a fresh AbortController for this request.
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId.current }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Read the SSE stream and dispatch each event through the same handler
      // we used with WebSocket — nothing changes here.
      for await (const event of readSSE(response)) {
        dispatch(event);
      }
    } catch (err) {
      if (err.name === "AbortError") return; // user cancelled — silent
      dispatch({ type: "run_error", message: err.message });
    } finally {
      abortRef.current = null;
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="chat-container">
      <header className="chat-header">
        <span className="chat-title">{title}</span>
        {/* No persistent connection to track — show spinner while waiting */}
        {waiting && <span className="header-spinner" />}
      </header>

      <div className="messages">
        {messages.map((msg) => (
          <Message key={msg.id} message={msg} />
        ))}

        {activity && (
          <div className="activity-row">
            <ActivityLog steps={activity.steps} sealed={activity.sealed} />
          </div>
        )}

        {waiting && !activity && messages[messages.length - 1]?.role === "user" && (
          <div className="message-row assistant">
            <div className="avatar">AI</div>
            <div className="bubble typing">
              <span /><span /><span />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="input-bar">
        <textarea
          ref={inputRef}
          className="input-field"
          rows={1}
          placeholder="Type a message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={waiting}
        />
        <button
          className="send-btn"
          onClick={sendMessage}
          disabled={!input.trim() || waiting}
        >
          Send
        </button>
      </div>
    </div>
  );
}
