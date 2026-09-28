"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";

export type KnowledgeFormState = { error?: string; message?: string };

export async function saveSource(
  _previous: KnowledgeFormState | null,
  formData: FormData,
): Promise<KnowledgeFormState> {
  const title = String(formData.get("title") ?? "").trim();
  const content = String(formData.get("content") ?? "").trim();
  const sourceId = String(formData.get("source_id") ?? "").trim();

  if (!title || !content) {
    return { error: "A document needs both a title and some text." };
  }

  try {
    const result = await apiFetch<{ source_id: string; chunk_count: number }>(
      "/knowledge",
      {
        method: "PUT",
        body: JSON.stringify({
          title,
          content,
          source_id: sourceId || null,
        }),
      },
    );
    revalidatePath("/knowledge");
    return {
      message: `Saved "${title}" as ${result.source_id}, indexed in ${result.chunk_count} ${
        result.chunk_count === 1 ? "piece" : "pieces"
      }.`,
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }
}

export async function removeSource(
  sourceId: string,
  _previous: KnowledgeFormState | null,
): Promise<KnowledgeFormState> {
  try {
    await apiFetch<void>(`/knowledge/${encodeURIComponent(sourceId)}`, {
      method: "DELETE",
    });
    revalidatePath("/knowledge");
    return { message: `Removed ${sourceId}.` };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }
}
