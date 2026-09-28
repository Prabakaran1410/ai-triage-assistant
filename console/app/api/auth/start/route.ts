import { redirect } from "next/navigation";

/**
 * Begin SSO. The API builds the WorkOS authorization URL because it holds
 * the WorkOS credentials; the console only sends the browser there.
 */
export async function GET(request: Request) {
  const organizationId = new URL(request.url).searchParams.get("organization_id");
  if (!organizationId) {
    redirect("/login?error=missing_organization");
  }

  const apiBaseUrl = process.env.API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("API_BASE_URL is not set");
  }

  const target = new URL(`${apiBaseUrl}/auth/login`);
  target.searchParams.set("organization_id", organizationId);
  redirect(target.toString());
}
