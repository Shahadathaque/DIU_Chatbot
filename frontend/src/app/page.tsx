"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  apiMode,
  checkEligibility,
  getPrograms,
  sendChatMessage,
} from "@/services/api";
import type {
  ChatResponse,
  EligibilityResponse,
  Language,
  Program,
  Source,
} from "@/types/api";

type Message = {
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
};

const prompts = [
  "What documents do I need?",
  "Check my eligibility",
  "Show available programs",
  "How do I apply?",
];

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [programs, setPrograms] = useState<Program[]>([]);
  const [eligibility, setEligibility] = useState<EligibilityResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const messagesEnd = useRef<HTMLDivElement>(null);

  useEffect(() => messagesEnd.current?.scrollIntoView({ behavior: "smooth" }), [messages, loading]);
  useEffect(() => { getPrograms().then(setPrograms).catch(() => setPrograms([])); }, []);

  async function submitMessage(event?: FormEvent) {
    event?.preventDefault();
    const message = input.trim();
    if (!message || loading) return;
    setInput(""); setError(""); setLoading(true);
    setMessages((current) => [...current, { role: "user", text: message }]);
    try {
      const response = await sendChatMessage({ message, language });
      if (!response.answer?.trim()) throw new Error("The assistant returned an empty answer.");
      setMessages((current) => [...current, { role: "assistant", text: response.answer, response }]);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The assistant is unavailable right now."); }
    finally { setLoading(false); }
  }

  async function submitEligibility(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setChecking(true); setEligibility(null);
    const data = new FormData(event.currentTarget);
    try { setEligibility(await checkEligibility({ program: String(data.get("program")), ssc_gpa: Number(data.get("ssc_gpa")), hsc_gpa: Number(data.get("hsc_gpa")), group: String(data.get("group")), diploma_status: String(data.get("diploma_status")) })); }
    catch { setEligibility({ status: "insufficient_information", reason: "We could not reach the eligibility service. Please try again." }); }
    finally { setChecking(false); }
  }

  return <main className="shell">
    <header className="topbar"><div className="brand"><span className="brand-mark">DIU</span><span><strong>Admission AI</strong><small>Research prototype</small></span></div><div className="top-actions"><span className="status"><i /> {apiMode === "mock" ? "Demo mode" : "Backend connected"}</span><select aria-label="Response language" value={language} onChange={(event) => setLanguage(event.target.value as Language)}><option value="en">English</option><option value="bn">বাংলা</option><option value="banglish">Banglish</option></select></div></header>
    <section className="hero"><p className="eyebrow">Daffodil International University</p><h1>Ask with confidence.<br /><em>Plan your next step.</em></h1><p className="hero-copy">A grounded admission assistant for programs, requirements, eligibility, and the application journey at DIU.</p></section>
    <div className="workspace"><section className="chat-panel" aria-label="Admission assistant chat"><div className="panel-heading"><div><p className="eyebrow">Conversation</p><h2>How can we help?</h2></div><button className="quiet-button" onClick={() => { setMessages([]); setError(""); }}>New chat</button></div>
      {messages.length === 0 && <div className="empty-state"><div className="empty-icon">✦</div><p>Start with a question about your DIU admission.</p><div className="prompt-grid">{prompts.map((prompt) => <button key={prompt} onClick={() => setInput(prompt)}>{prompt}<span>↗</span></button>)}</div></div>}
      <div className="messages">{messages.map((message, index) => <article className={`message ${message.role}`} key={`${message.text}-${index}`}><span className="message-label">{message.role === "user" ? "You" : "DIU assistant"}</span><p>{message.text}</p>{message.response?.sources?.length ? <Sources sources={message.response.sources} /> : null}</article>)}{loading && <article className="message assistant"><span className="message-label">DIU assistant</span><div className="typing"><i /><i /><i /></div></article>}<div ref={messagesEnd} /></div>
      {error && <div className="error" role="alert">{error} <button onClick={() => setError("")}>Dismiss</button></div>}<form className="chat-form" onSubmit={submitMessage}><input aria-label="Ask about DIU admission" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about admission, programs, or eligibility..." /><button aria-label="Send question" type="submit">↑</button></form>
    </section><aside className="side-panel"><section className="tool-section"><div className="section-title"><span className="number">01</span><div><p className="eyebrow">Decision support</p><h2>Check eligibility</h2></div></div><form className="eligibility-form" onSubmit={submitEligibility}><label>Desired program<select name="program" defaultValue="CSE"><option>CSE</option><option>SWE</option><option>BBA</option></select></label><div className="field-row"><label>SSC GPA<input name="ssc_gpa" type="number" min="0" max="5" step="0.01" placeholder="4.50" required /></label><label>HSC GPA<input name="hsc_gpa" type="number" min="0" max="5" step="0.01" placeholder="4.20" required /></label></div><label>Academic group<select name="group" defaultValue="Science"><option>Science</option><option>Business Studies</option><option>Humanities</option><option>Diploma</option></select></label><label>Diploma status<select name="diploma_status" defaultValue="Not applicable"><option>Not applicable</option><option>Currently enrolled</option><option>Completed</option></select></label><button className="primary-button" disabled={checking}>{checking ? "Checking..." : "Check with DIU rules"}</button></form>{eligibility && <div className={`result ${eligibility.status}`}><strong>{eligibility.status === "eligible" ? "Eligible" : eligibility.status === "not_eligible" ? "Not eligible" : "Insufficient information"}</strong><p>{eligibility.reason}</p>{eligibility.source && <a href={eligibility.source} target="_blank" rel="noreferrer">View source ↗</a>}</div>}</section>
      <section className="tool-section programs"><div className="section-title"><span className="number">02</span><div><p className="eyebrow">Explore</p><h2>Programs</h2></div></div>{programs.length ? programs.map((program) => <div className="program" key={program.name}><div><strong>{program.name}</strong><small>{program.degree ?? "Program"} · {program.faculty ?? "DIU"}</small></div><span>→</span></div>) : <p className="muted">Program information is unavailable.</p>}</section></aside></div>
    <footer>This AI assistant is a research prototype. For final admission decisions, verify information through <a href="https://daffodilvarsity.edu.bd/" target="_blank" rel="noreferrer">official DIU sources</a>.</footer>
  </main>;
}

function Sources({ sources }: { sources: Source[] }) { return <div className="sources"><span>Sources</span>{sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title} ↗</a>)}</div>; }
