import { redirect } from "next/navigation";

import { getSessionToken } from "@/lib/session";

export default async function HomePage() {
  redirect((await getSessionToken()) ? "/queue" : "/login");
}
