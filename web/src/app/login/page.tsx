import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE, checkLogin, makeSession, requestAccount } from "@/lib/accounts";

export const metadata: Metadata = { title: "Sign in · EnerZen" };

const field = (form: FormData, key: string) => String(form.get(key) ?? "").trim();
const back = (params: Record<string, string>) => redirect(`/login?${new URLSearchParams(params)}`);

async function signIn(form: FormData) {
  "use server";
  const email = field(form, "email").toLowerCase();
  const error = checkLogin(email, String(form.get("password") ?? ""));
  if (error) back({ error });
  const { value, maxAge } = makeSession(email);
  const https = (await headers()).get("x-forwarded-proto") === "https";
  (await cookies()).set(SESSION_COOKIE, value, { httpOnly: true, sameSite: "lax", secure: https, maxAge, path: "/" });
  redirect("/");
}

async function askForAccess(form: FormData) {
  "use server";
  const email = field(form, "email").toLowerCase();
  const password = String(form.get("password") ?? "");
  if (!/^\S+@\S+\.\S+$/.test(email)) back({ error: "Enter a valid email." });
  if (password.length < 8) back({ error: "Use a password of at least 8 characters." });
  const error = requestAccount(email, field(form, "name").slice(0, 100), field(form, "note").slice(0, 500), password);
  back(error ? { error } : { sent: "1" });
}

const input = "w-full rounded-lg border border-[#d5d9ec] bg-white px-3 py-2";
const button = "w-full rounded-lg bg-[var(--brand-blue)] px-4 py-2 font-medium text-white hover:opacity-90";

export default async function Login({ searchParams }: PageProps<"/login">) {
  const { error, sent } = await searchParams;
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-8 px-6 py-12">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/enerzen-logo.svg" alt="EnerZen" className="h-10 self-start" />
      <p>EnerZen is private for now. Sign in, or ask for an account and we&apos;ll let you know once it&apos;s approved.</p>
      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-red-800">{error}</p>}
      {sent && <p role="status" className="rounded-lg bg-green-50 px-3 py-2 text-green-800">Request sent. You can sign in once it&apos;s approved.</p>}

      <form action={signIn} className="flex flex-col gap-3">
        <h1 className="text-xl font-medium">Sign in</h1>
        <label>Email<input name="email" type="email" autoComplete="email" required className={input} /></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" required className={input} /></label>
        <button className={button}>Sign in</button>
      </form>

      <form action={askForAccess} className="flex flex-col gap-3 border-t border-[#d5d9ec] pt-8">
        <h2 className="text-xl font-medium">Request an account</h2>
        <label>Name<input name="name" autoComplete="name" required className={input} /></label>
        <label>Email<input name="email" type="email" autoComplete="email" required className={input} /></label>
        <label>Password<input name="password" type="password" autoComplete="new-password" minLength={8} required className={input} /></label>
        <label>What will you use it for? <span className="opacity-70">(optional)</span><textarea name="note" rows={2} maxLength={500} className={input} /></label>
        <button className={button}>Request access</button>
      </form>
    </main>
  );
}
