import type { ExamRubric } from "@/types/barem";

import type { AssistantReply } from "./fromDraft";

const API_BASE = "/api/v1/barem-assistant";

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body);
  } catch {
    return `HTTP ${res.status}`;
  }
}

export interface ExtractedDocument {
  filename: string;
  chars: number;
  text: string;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

/** Plain text of a .pdf/.docx exam, for the assistant to read. */
export async function extractDocument(file: File): Promise<ExtractedDocument> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/extract`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** One assistant turn. Stateless server-side: history and draft go with every call. */
export async function chatAssistant(
  messages: ChatTurn[],
  exam: ExamRubric,
  documentText: string | null,
): Promise<AssistantReply> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, exam, document_text: documentText }),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}
