import { NextResponse } from "next/server";

import { clearSessionToken } from "@/lib/session";

export async function POST(request: Request) {
  await clearSessionToken();
  return NextResponse.redirect(new URL("/login", request.url), { status: 303 });
}
