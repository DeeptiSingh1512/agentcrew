import { useState, type ChangeEvent } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";

const API = "http://localhost:8000";

type Step = { agent: string; message: string };
type Evidence = { label: string; text: string; score?: number; url?: string };

const ICONS: Record<string, string> = {
  planner: "🧭",
  retriever: "🔎",
  writer: "✍️",
  critic: "🧐",
  web_researcher: "🌐",
  analyst: "📊",
};

export default function App() {
  const [uploadMsg, setUploadMsg] = useState("");
  const [goal, setGoal] = useState("Summarize the skills and work experience");
  const [steps, setSteps] = useState<Step[]>([]);
  const [report, setReport] = useState("");
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [status, setStatus] = useState("");
  const [running, setRunning] = useState(false);

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadMsg("Uploading...");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API}/upload`, { method: "POST", body: form });
      const data = await res.json();
      setUploadMsg(
        res.ok
          ? `Stored ${data.chunks} chunks from ${data.filename}`
          : `Error: ${JSON.stringify(data.detail)}`
      );
    } catch {
      setUploadMsg("Could not reach the server. Is it running?");
    }
  }

  async function run() {
    setSteps([]);
    setReport("");
    setEvidence([]);
    setStatus("");
    setRunning(true);
    try {
      const res = await fetch(`${API}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      if (!res.ok || !res.body) {
        setStatus(`Error ${res.status}`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          const ev = JSON.parse(part.slice(6));
          if (ev.type === "step") {
            setSteps((s) => [...s, { agent: ev.agent, message: ev.message }]);
          } else if (ev.type === "done") {
            setReport(ev.report);
            setEvidence(ev.evidence ?? []);
            setStatus(
              `${ev.approved ? "Approved by critic" : "Not approved"} after ${ev.drafts} draft(s)`
            );
          } else if (ev.type === "error") {
            setStatus(`Error: ${ev.message}`);
          }
        }
      }
    } catch {
      setStatus("Connection failed. Is the server running?");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="page">
      <h1>AgentCrew</h1>
      <p className="sub">A crew of AI agents that plans, researches, writes, and reviews.</p>

      <section className="card">
        <h2>1. Upload a PDF</h2>
        <input type="file" accept="application/pdf" onChange={upload} />
        {uploadMsg && <p className="note">{uploadMsg}</p>}
      </section>

      <section className="card">
        <h2>2. Give the crew a goal</h2>
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} />
        <button onClick={run} disabled={running || goal.trim().length < 3}>
          {running ? "Crew is working..." : "Run crew"}
        </button>
      </section>

      {steps.length > 0 && (
        <section className="card">
          <h2>Live agent trace</h2>
          <ol className="timeline">
            {steps.map((s, i) => (
              <li key={i}>
                <span className="agent">
                  {ICONS[s.agent] ?? "🤖"} {s.agent.replace("_", " ")}
                </span>
                <span className="msg">{s.message}</span>
              </li>
            ))}
            {running && <li className="pending">working...</li>}
          </ol>
        </section>
      )}

      {status && <p className="status">{status}</p>}

      {report && (
        <section className="card">
          <h2>Report</h2>
          <ReactMarkdown>{report}</ReactMarkdown>
        </section>
      )}

      {evidence.length > 0 && (
        <section className="card">
          <h2>Sources</h2>
          {evidence.map((e, i) => (
            <details key={i}>
             <summary>
              {e.label}
              {e.score !== undefined ? ` (score ${e.score})` : ""}
            </summary>
            {e.url && (
             <p>
               <a href={e.url} target="_blank" rel="noreferrer">{e.url}</a>
             </p>
            
          )}
          <p className="snippet">{e.text}</p>
         </details>
          ))}
        </section>
      )}
    </div>
  );
}