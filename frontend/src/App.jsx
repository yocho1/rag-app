import React, { useState } from "react";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:5004";

export default function App() {
  const [file, setFile] = useState(null);
  const [ingestStatus, setIngestStatus] = useState(null);
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState(null);
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(false);

  const upload = async (e) => {
    e.preventDefault();
    if (!file) return alert("Choose a file");
    setIngestStatus("Uploading...");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await axios.post(`${API}/ingest`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setIngestStatus(`Ingested ${res.data.ingested_chunks} chunks from ${res.data.file}`);
    } catch (err) {
      setIngestStatus("Upload failed: " + (err?.response?.data?.error || err.message));
    }
  };

  const ask = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setAnswer(null);
    setDocs([]);
    try {
      const res = await axios.post(`${API}/query`, { query, top_k: 4 });
      setAnswer(res.data.answer);
      setDocs(res.data.documents || []);
    } catch (err) {
      setAnswer("Error: " + (err?.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6 flex items-start justify-center">
      <div className="w-full max-w-3xl bg-white rounded-xl shadow-lg p-6">
        <h1 className="text-2xl font-bold mb-4">RAG Demo — Ingest & Query</h1>

        <section className="mb-6">
          <h2 className="font-semibold mb-2">Ingest a document</h2>
          <form onSubmit={upload} className="flex gap-2 items-center">
            <input type="file" onChange={(e) => setFile(e.target.files?.[0])} />
            <button type="submit" className="px-4 py-2 bg-sky-600 text-white rounded">Upload</button>
          </form>
          <div className="mt-2 text-sm text-slate-600">{ingestStatus}</div>
        </section>

        <section className="mb-6">
          <h2 className="font-semibold mb-2">Ask a question</h2>
          <div className="flex gap-2">
            <input value={query} onChange={(e)=>setQuery(e.target.value)} className="flex-1 p-2 border rounded" placeholder="e.g., How to create Etsy listing?" />
            <button onClick={ask} className="px-4 py-2 bg-emerald-600 text-white rounded" disabled={loading}>{loading ? "Searching..." : "Ask"}</button>
          </div>
        </section>

        <section>
          <h3 className="font-semibold">Answer</h3>
          <div className="mt-2 p-4 bg-gray-50 rounded min-h-[80px]">{answer || "No answer yet"}</div>
        </section>

        <section className="mt-4">
          <h3 className="font-semibold">Retrieved Chunks</h3>
          <div className="mt-2 space-y-2">
            {docs.length === 0 && <div className="text-sm text-slate-500">No retrieved documents</div>}
            {docs.map((d, i) => (
              <div key={i} className="p-3 border rounded bg-white">
                <div className="text-xs text-slate-400">source: {d.metadata?.source || "unknown"} · distance: {d.distance?.toFixed(4)}</div>
                <div className="mt-1 text-sm">{d.text}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
