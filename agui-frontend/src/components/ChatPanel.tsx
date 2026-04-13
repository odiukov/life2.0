import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    if (!input.trim() || loading) return;
    const userMessage = input.trim();
    setInput("");

    setMessages(prev => [
      ...prev,
      { role: "user", content: userMessage },
      { role: "assistant", content: "", streaming: true },
    ]);
    setLoading(true);

    try {
      const res = await fetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [{ role: "user", content: userMessage }],
        }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "TextMessageContent") {
              setMessages(prev => {
                const msgs = [...prev];
                const last = msgs[msgs.length - 1];
                if (last?.role === "assistant") {
                  msgs[msgs.length - 1] = { ...last, content: last.content + event.delta };
                }
                return msgs;
              });
            }
          } catch { /* skip malformed lines */ }
        }
      }
    } catch {
      setMessages(prev => {
        const msgs = [...prev];
        msgs[msgs.length - 1] = { role: "assistant", content: "Error: could not reach backend." };
        return msgs;
      });
    }

    setMessages(prev => {
      const msgs = [...prev];
      const last = msgs[msgs.length - 1];
      if (last?.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, streaming: false };
      }
      return msgs;
    });
    setLoading(false);
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#0d0d1a", fontFamily: "monospace", overflow: "hidden" }}>
      <div style={{ padding: "10px 16px", borderBottom: "1px solid #1e1e30", fontSize: "12px", color: "#4a9eff" }}>
        life-agents
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        {messages.length === 0 && (
          <div style={{ color: "#555", fontSize: "12px" }}>Ask about your sleep, workouts, or nutrition.</div>
        )}
        {messages.map((msg, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: "4px", alignItems: msg.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{ fontSize: "10px", color: "#555" }}>{msg.role === "user" ? "you" : "agent"}</div>
            <div style={{
              background: msg.role === "user" ? "#1a1a2e" : "#0f0f1a",
              border: `1px solid ${msg.role === "user" ? "#2a2a4e" : "#1e1e30"}`,
              borderRadius: "4px",
              padding: "8px 12px",
              fontSize: "13px",
              color: "#e0e0e0",
              maxWidth: "80%",
            }}>
              {msg.role === "user" ? (
                <span style={{ whiteSpace: "pre-wrap" }}>{msg.content}</span>
              ) : (
                <ReactMarkdown components={{
                  p: ({ children }) => <p style={{ margin: "4px 0", lineHeight: 1.6 }}>{children}</p>,
                  h1: ({ children }) => <h1 style={{ fontSize: "15px", fontWeight: "bold", margin: "8px 0 4px", color: "#7ab8ff" }}>{children}</h1>,
                  h2: ({ children }) => <h2 style={{ fontSize: "14px", fontWeight: "bold", margin: "8px 0 4px", color: "#7ab8ff" }}>{children}</h2>,
                  h3: ({ children }) => <h3 style={{ fontSize: "13px", fontWeight: "bold", margin: "6px 0 4px", color: "#7ab8ff" }}>{children}</h3>,
                  strong: ({ children }) => <strong style={{ color: "#b0d4ff" }}>{children}</strong>,
                  em: ({ children }) => <em style={{ color: "#aaa" }}>{children}</em>,
                  ul: ({ children }) => <ul style={{ margin: "4px 0", paddingLeft: "18px" }}>{children}</ul>,
                  ol: ({ children }) => <ol style={{ margin: "4px 0", paddingLeft: "18px" }}>{children}</ol>,
                  li: ({ children }) => <li style={{ margin: "2px 0", lineHeight: 1.5 }}>{children}</li>,
                  table: ({ children }) => <table style={{ borderCollapse: "collapse", width: "100%", margin: "8px 0", fontSize: "12px" }}>{children}</table>,
                  th: ({ children }) => <th style={{ border: "1px solid #2a2a4e", padding: "4px 8px", background: "#1a1a2e", color: "#7ab8ff", textAlign: "left" }}>{children}</th>,
                  td: ({ children }) => <td style={{ border: "1px solid #1e1e30", padding: "4px 8px" }}>{children}</td>,
                  code: ({ children }) => <code style={{ background: "#1a1a2e", padding: "1px 4px", borderRadius: "3px", fontSize: "12px", color: "#ff9e64" }}>{children}</code>,
                  pre: ({ children }) => <pre style={{ background: "#1a1a2e", padding: "8px", borderRadius: "4px", overflowX: "auto", margin: "6px 0" }}>{children}</pre>,
                  hr: () => <hr style={{ border: "none", borderTop: "1px solid #1e1e30", margin: "8px 0" }} />,
                  blockquote: ({ children }) => <blockquote style={{ borderLeft: "2px solid #4a9eff", paddingLeft: "8px", margin: "4px 0", color: "#aaa" }}>{children}</blockquote>,
                }}>
                  {msg.content}
                </ReactMarkdown>
              )}
              {msg.streaming && msg.content === "" && (
                <span style={{ display: "inline-flex", gap: "4px", alignItems: "center", padding: "2px 0" }}>
                  {[0, 1, 2].map(j => (
                    <span key={j} style={{
                      width: "6px", height: "6px", borderRadius: "50%",
                      background: "#4a9eff", display: "inline-block",
                      animation: "pulse 1.2s ease-in-out infinite",
                      animationDelay: `${j * 0.2}s`,
                    }} />
                  ))}
                </span>
              )}
              {msg.streaming && msg.content !== "" && <span style={{ opacity: 0.5 }}>▋</span>}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: "12px 16px", borderTop: "1px solid #1e1e30", display: "flex", gap: "8px" }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
          placeholder="Ask your agents..."
          disabled={loading}
          style={{
            flex: 1,
            background: "#13131f",
            border: "1px solid #1e1e30",
            borderRadius: "4px",
            color: "#e0e0e0",
            fontFamily: "monospace",
            fontSize: "13px",
            padding: "8px 12px",
            outline: "none",
          }}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          style={{
            background: loading ? "#1a1a2e" : "#1a3a6e",
            border: "1px solid #2a4a8e",
            borderRadius: "4px",
            color: "#4a9eff",
            fontFamily: "monospace",
            fontSize: "13px",
            padding: "8px 16px",
            cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? "..." : "send"}
        </button>
      </div>
    </div>
  );
}
