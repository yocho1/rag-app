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
      setIngestStatus(`✅ Successfully ingested ${res.data.ingested_chunks} chunks from ${res.data.file}`);
    } catch (err) {
      setIngestStatus("❌ Upload failed: " + (err?.response?.data?.error || err.message));
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
      setAnswer("❌ Error: " + (err?.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !loading) {
      ask();
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 p-4 md:p-6">
      {/* Header */}
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-8">
          <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent mb-4">
            Smart Document Assistant
          </h1>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Upload your documents and ask questions. Powered by AI and semantic search.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Input Section */}
          <div className="space-y-6">
            {/* File Upload Card */}
            <div className="bg-white rounded-2xl shadow-xl p-6 border border-gray-100">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold text-gray-800">Upload Document</h2>
              </div>
              
              <form onSubmit={upload} className="space-y-4">
                <div className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center hover:border-blue-400 transition-colors">
                  <input 
                    type="file" 
                    onChange={(e) => setFile(e.target.files?.[0])}
                    className="hidden" 
                    id="file-upload"
                    accept=".pdf,.docx,.txt"
                  />
                  <label htmlFor="file-upload" className="cursor-pointer">
                    <svg className="w-12 h-12 text-gray-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                    </svg>
                    <p className="text-gray-600 mb-2">
                      {file ? file.name : "Choose PDF, DOCX, or TXT file"}
                    </p>
                    <p className="text-sm text-gray-500">Max file size: 10MB</p>
                  </label>
                </div>
                
                <button 
                  type="submit" 
                  disabled={!file}
                  className="w-full bg-gradient-to-r from-blue-600 to-blue-700 text-white py-3 px-4 rounded-xl font-semibold hover:from-blue-700 hover:to-blue-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" />
                  </svg>
                  Process Document
                </button>
              </form>
              
              {ingestStatus && (
                <div className={`mt-4 p-3 rounded-lg text-sm ${
                  ingestStatus.includes('✅') 
                    ? 'bg-green-50 text-green-700 border border-green-200' 
                    : 'bg-red-50 text-red-700 border border-red-200'
                }`}>
                  {ingestStatus}
                </div>
              )}
            </div>

            {/* Query Card */}
            <div className="bg-white rounded-2xl shadow-xl p-6 border border-gray-100">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-emerald-100 rounded-lg">
                  <svg className="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold text-gray-800">Ask Questions</h2>
              </div>

              <div className="space-y-4">
                <div className="relative">
                  <input 
                    value={query} 
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyPress={handleKeyPress}
                    className="w-full p-4 pr-12 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-lg"
                    placeholder="What would you like to know about your document?"
                    disabled={loading}
                  />
                  <button 
                    onClick={ask} 
                    disabled={loading || !query.trim()}
                    className="absolute right-2 top-1/2 transform -translate-y-1/2 bg-gradient-to-r from-emerald-500 to-emerald-600 text-white p-2 rounded-lg hover:from-emerald-600 hover:to-emerald-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loading ? (
                      <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                      </svg>
                    )}
                  </button>
                </div>
                
                <div className="text-sm text-gray-500 flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Press Enter or click the arrow to search
                </div>
              </div>
            </div>
          </div>

          {/* Right Column - Results Section */}
          <div className="space-y-6">
            {/* Answer Card */}
            <div className="bg-white rounded-2xl shadow-xl p-6 border border-gray-100 h-fit">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-purple-100 rounded-lg">
                  <svg className="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold text-gray-800">AI Answer</h2>
              </div>

              <div className="min-h-[200px]">
                {answer ? (
                  <div className="prose prose-lg max-w-none">
                    <div className="bg-gradient-to-r from-purple-50 to-blue-50 p-6 rounded-xl border border-purple-100">
                      <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{answer}</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-48 text-gray-400">
                    <div className="text-center">
                      <svg className="w-12 h-12 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                      </svg>
                      <p>Ask a question to get an AI-powered answer</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Retrieved Documents Card */}
            <div className="bg-white rounded-2xl shadow-xl p-6 border border-gray-100">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-orange-100 rounded-lg">
                  <svg className="w-6 h-6 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold text-gray-800">Retrieved Sources</h2>
                {docs.length > 0 && (
                  <span className="bg-orange-100 text-orange-800 text-sm px-2 py-1 rounded-full">
                    {docs.length} found
                  </span>
                )}
              </div>

              <div className="space-y-4 max-h-96 overflow-y-auto">
                {docs.length === 0 ? (
                  <div className="text-center py-8 text-gray-400">
                    <svg className="w-12 h-12 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p>No sources retrieved yet</p>
                  </div>
                ) : (
                  docs.map((d, i) => (
                    <div key={i} className="p-4 border border-gray-200 rounded-xl hover:border-blue-300 transition-colors bg-white">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-1 rounded">
                          {d.metadata?.source || "Unknown source"}
                        </span>
                        <span className="text-xs text-gray-500">
                          Relevance: {(1 - (d.distance || 0)).toFixed(3)}
                        </span>
                      </div>
                      <p className="text-sm text-gray-700 leading-relaxed line-clamp-3">
                        {d.text}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
       {/* Footer */}
{/* Footer */}
<div className="text-center mt-8 pt-6 border-t border-gray-200">
  <p className="text-gray-500 text-sm">
    Built by{" "}
    <a 
      href="https://www.linkedin.com/in/achraf-lachgar/" 
      target="_blank" 
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 font-semibold transition-colors hover:underline"
    >
      achraflachgar.me
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
      </svg>
    </a>
  </p>
</div>
      </div>
    </div>
  );
}