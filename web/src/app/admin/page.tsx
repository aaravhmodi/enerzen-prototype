import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { SESSION_COOKIE, isAdmin, loadAccounts, sessionEmail, setStatus } from "@/lib/accounts";

export const metadata: Metadata = { title: "Accounts · EnerZen" };
export const dynamic = "force-dynamic";

// The proxy has already required an approved account; this page also needs an admin.
async function adminEmail() {
  const email = await sessionEmail((await cookies()).get(SESSION_COOKIE)?.value);
  return email && isAdmin(email) ? email : null;
}

async function decide(form: FormData) {
  "use server";
  const me = await adminEmail();
  const email = String(form.get("email"));
  const status = form.get("status") === "approved" ? "approved" : "removed";
  if (!me || email === me) return; // admins can't lock themselves out
  await setStatus(email, status);
  redirect("/admin");
}

export default async function Admin() {
  const me = await adminEmail();
  if (!me) notFound();
  const accounts = await loadAccounts(); // waiting requests first
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <h1 className="mb-6 text-2xl font-medium">Accounts</h1>
      <ul className="flex flex-col gap-3">
        {accounts.map((a) => (
          <li key={a.email} className="flex flex-wrap items-center gap-4 rounded-lg border border-[#d5d9ec] bg-white p-4">
            <div className="flex-1">
              <p className="font-medium">{a.name} · {a.email}</p>
              <p className="opacity-70">
                {a.status === "pending" ? "Waiting" : "Approved"} · asked {a.requested_at.toISOString().slice(0, 10)}
                {a.note && ` · “${a.note}”`}
              </p>
            </div>
            {a.email !== me && (
              <form action={decide} className="flex gap-2">
                <input type="hidden" name="email" value={a.email} />
                {a.status === "pending" && (
                  <button name="status" value="approved" className="rounded-lg bg-[var(--brand-blue)] px-3 py-1 text-white">Approve</button>
                )}
                <button name="status" value="removed" className="rounded-lg border border-[#d5d9ec] px-3 py-1">
                  {a.status === "pending" ? "Decline" : "Remove"}
                </button>
              </form>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
