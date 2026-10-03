import { useState, type ChangeEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";

const API = "http://localhost:8000";

type Step = { agent: string; message: string };
type Evidence = { label: string; text: string; score?: number; url?: string };
type PlanItem = { q: string; source: "docs" | "web" };

const ICONS: Record<string, string> = {
  planner: "🧭",
  retriever: "🔎",
  web_researcher: "🌐",
  analyst: "📊",
  writer: "✍️",
  critic: "🧐",
};

export default function App() {
  const [uploadMsg, setUploadMsg] = useState("");
  const [goal, setGoal] = useState("Summarize the skills and work experience");
  const [plan, setPlan] = useState<PlanItem[] | null>(null);
  const [planning, setPlanning] = useState(false);
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

  function resetResults() {
    setSteps([]);
    setReport("");
    setEvidence([]);
    setStatus("");
  }

  async function getPlan() {
    resetResults();
    setPlan(null);
    setPlanning(true);
    try {
      const res = await fetch(`${API}/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(`Error: ${JSON.stringify(data.detail)}`);
        return;
      }
      setPlan(data.plan);
    } catch {
      setStatus("Could not reach the server. Is it running?");
    } finally {
      setPlanning(false);
    }
  }

  function updateItem(i: number, patch: Partial<PlanItem>) {
    setPlan((p) => (p ? p.map((it, idx) => (idx === i ? { ...it, ...patch } : it)) : p));
  }
  function removeItem(i: number) {
    setPlan((p) => (p ? p.filter((_, idx) => idx !== i) : p));
  }
  function addItem() {
    setPlan((p) => (p && p.length < 4 ? [...p, { q: "", source: "docs" }] : p));
  }

  async function run() {
    if (!plan) return;
    const approved = plan.filter((p) => p.q.trim().length >= 3);
    if (approved.length === 0) return;
    resetResults();
    setRunning(true);
    try {
      const res = await fetch(`${API}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal, plan: approved }),
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

  const busy = running || planning;

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
        <textarea
          value={goal}
          onChange={(e) => {
            setGoal(e.target.value);
            setPlan(null);
          }}
          rows={3}
        />
        <button onClick={getPlan} disabled={busy || goal.trim().length < 3}>
          {planning ? "Planning..." : "Create plan"}
        </button>
      </section>

      {plan && (
        <section className="card">
          <h2>3. Review and approve the plan</h2>
          {plan.map((item, i) => (
            <div className="plan-item" key={i}>
              <input
                type="text"
                value={item.q}
                disabled={running}
                onChange={(e) => updateItem(i, { q: e.target.value })}
              />
              <select
                value={item.source}
                disabled={running}
                onChange={(e) => updateItem(i, { source: e.target.value as "docs" | "web" })}
              >
                <option value="docs">documents</option>
                <option value="web">web</option>
              </select>
              <button className="small" disabled={running} onClick={() => removeItem(i)}>
                ✕
              </button>
            </div>
          ))}
          <div className="row">
            {plan.length < 4 && (
              <button className="small" disabled={running} onClick={addItem}>
                + Add question
              </button>
            )}
            <button
              onClick={run}
              disabled={running || plan.every((p) => p.q.trim().length < 3)}
            >
              {running ? "Crew is working..." : "Approve & run"}
            </button>
          </div>
        </section>
      )}

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
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
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
                  <a href={e.url} target="_blank" rel="noreferrer">
                    {e.url}
                  </a>
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