/* eslint-disable @typescript-eslint/no-unused-vars */
"use client";

import { useState } from "react";
type SourceMetadata = {
  document_id: string;
  chunk_index: number;
  filename: string;
};

type SourceChunk = {
  text: string;
  metadata: SourceMetadata;
};

export default function Home() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<SourceChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState("");


  async function askQuestion() {
    if (!question.trim()) return;

    setLoading(true);
    setError("");
    setAnswer("");
    setSources([]);

    try {
      const res = await fetch("http://localhost:8000/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) {
        throw new Error("Backend error");
      }

      const data = await res.json();
      setAnswer(data.answer);
      setSources(data.sources || []);
    } catch (err) {
      setError("Failed to fetch answer from backend.");
    } finally {
      setLoading(false);
    }
  }
  async function uploadDocument() {
  if (!file) {
    setUploadStatus("Please select a file first.");
    return;
  }

  setUploadStatus("Uploading...");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("http://localhost:8000/documents/upload", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      throw new Error("Upload failed");
    }

    setUploadStatus("✅ Document uploaded and indexed successfully.");
    setFile(null);
  } catch (err) {
    setUploadStatus("❌ Failed to upload document.");
  }
}


  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <div className="mb-6 border-b pb-4">
  <h2 className="font-semibold mb-2">Upload Document</h2>

  <input
    type="file"
    accept=".pdf"
    onChange={(e) => setFile(e.target.files?.[0] || null)}
    className="mb-2"
  />

  <button
    onClick={uploadDocument}
    className="bg-blue-600 text-white px-4 py-1 rounded"
  >
    Upload
  </button>

  {uploadStatus && (
    <p className="text-sm mt-2">{uploadStatus}</p>
  )}
</div>

      <div className="max-w-3xl mx-auto bg-white rounded-xl shadow p-6">
        <h1 className="text-2xl font-bold mb-2">
          AI Knowledge Assistant
        </h1>
        <p className="text-sm text-gray-600 mb-4">
          Ask questions grounded in your uploaded documents
        </p>

        <textarea
          className="w-full border rounded p-3 mb-4"
          rows={4}
          placeholder="Ask a question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />

        <button
          onClick={askQuestion}
          disabled={loading}
          className="bg-black text-white px-5 py-2 rounded disabled:opacity-50"
        >
          {loading ? "Thinking..." : "Ask"}
        </button>

        {error && (
          <p className="text-red-500 mt-4">{error}</p>
        )}

        {answer && (
          <div className="mt-6">
            <h2 className="font-semibold mb-2">Answer</h2>
            <p className="whitespace-pre-wrap text-gray-800">
              {answer}
            </p>
          </div>
        )}

        {sources.length > 0 && (
          <div className="mt-6">
            <h2 className="font-semibold mb-2">Sources</h2>
            <ul className="space-y-2 text-sm">
              {sources.map((s, i) => (
                <li
                  key={i}
                  className="border rounded p-3 bg-gray-50"
                >
                  <strong>Chunk {i + 1}</strong>
                  <p className="mt-1 text-gray-700">
                    {s.text.slice(0, 300)}…
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </main>
  );
}
