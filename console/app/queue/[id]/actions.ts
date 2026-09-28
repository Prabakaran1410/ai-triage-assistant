"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch, type EventDetail } from "@/lib/api";

/**
 * Server actions, so the session token stays on the server and the browser
 * never holds it. The API re-checks the caller's role and the status
 * transition regardless of what the console allows.
 */
export async function reviewAction(
  eventId: string,
  _previous: { error?: string } | null,
  formData: FormData,
): Promise<{ error?: string }> {
  const action = String(formData.get("action") ?? "");
  const finalReply = formData.get("final_reply");
  const note = formData.get("note");

  try {
    await apiFetch<EventDetail>(`/events/${eventId}/review`, {
      method: "POST",
      body: JSON.stringify({
        action,
        final_reply: typeof finalReply === "string" && finalReply.trim() ? finalReply : null,
        note: typeof note === "string" && note.trim() ? note : null,
      }),
    });
  } catch (error) {
    if (error instanceof ApiError) {
      // 409 means somebody else already acted on this item, or the
      // transition is not allowed from its current status.
      return { error: error.message };
    }
    throw error;
  }

  revalidatePath(`/queue/${eventId}`);
  revalidatePath("/queue");
  return {};
}
