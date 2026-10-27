// Who may use the site: accounts in the home server's shared Postgres (DATABASE_URL,
// tables enerzen_*), like the other homelab projects.
import { createHmac, randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { Pool } from "pg";

export type Account = {
  email: string;
  name: string;
  note: string;
  status: "pending" | "approved";
  requested_at: Date;
};

export const SESSION_COOKIE = "enerzen_session";
const SESSION_DAYS = 30;

const admins = () =>
  (process.env.ADMIN_EMAILS ?? "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
export const isAdmin = (email: string) => admins().includes(email);

const pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 3 });

// Tables made on first use, so a fresh database needs no migration step.
let ready: Promise<unknown> | null = null;
async function db<T>(sql: string, params: unknown[] = []) {
  ready ??= pool.query(`
    CREATE TABLE IF NOT EXISTS enerzen_accounts (
      email text PRIMARY KEY, name text NOT NULL, note text NOT NULL,
      hash text NOT NULL, status text NOT NULL, requested_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS enerzen_settings (key text PRIMARY KEY, value text NOT NULL);`)
    .catch((e) => { ready = null; throw e; });
  await ready;
  return (await pool.query(sql, params)).rows as T[];
}

export const loadAccounts = () =>
  db<Account>("SELECT email, name, note, status, requested_at FROM enerzen_accounts ORDER BY status DESC, requested_at");

function hashPassword(password: string) {
  const salt = randomBytes(16).toString("hex");
  return `${salt}:${scryptSync(password, salt, 64).toString("hex")}`;
}

function passwordMatches(password: string, stored: string) {
  const [salt, hex] = stored.split(":");
  return timingSafeEqual(scryptSync(password, salt, 64), Buffer.from(hex, "hex"));
}

// Returns an error to show, or null. Admins (ADMIN_EMAILS) are approved on request.
export async function requestAccount(email: string, name: string, note: string, password: string) {
  const added = await db(
    `INSERT INTO enerzen_accounts (email, name, note, hash, status) VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (email) DO NOTHING RETURNING email`,
    [email, name, note, hashPassword(password), isAdmin(email) ? "approved" : "pending"],
  );
  return added.length ? null : "That email has already asked for access.";
}

export async function checkLogin(email: string, password: string) {
  const [account] = await db<{ hash: string; status: string }>(
    "SELECT hash, status FROM enerzen_accounts WHERE email = $1", [email]);
  if (!account || !passwordMatches(password, account.hash)) return "Wrong email or password.";
  if (account.status !== "approved") return "Your request is waiting for approval.";
  return null;
}

export async function setStatus(email: string, status: "approved" | "removed") {
  await (status === "removed"
    ? db("DELETE FROM enerzen_accounts WHERE email = $1", [email])
    : db("UPDATE enerzen_accounts SET status = 'approved' WHERE email = $1", [email]));
}

// Kept beside the accounts so sessions survive rebuilds without another setting.
let secret: string | null = null;
async function sign(value: string) {
  if (!secret) {
    await db("INSERT INTO enerzen_settings VALUES ('session_secret', $1) ON CONFLICT DO NOTHING",
      [randomBytes(32).toString("hex")]);
    [{ value: secret }] = await db<{ value: string }>("SELECT value FROM enerzen_settings WHERE key = 'session_secret'");
  }
  return createHmac("sha256", secret!).update(value).digest("hex");
}

export async function makeSession(email: string) {
  const value = `${email}|${Date.now() + SESSION_DAYS * 86_400_000}`;
  return { value: `${value}|${await sign(value)}`, maxAge: SESSION_DAYS * 86_400 };
}

// The signed-in email, only while the cookie is genuine, unexpired and the account
// still approved, so removing someone signs them out on their next request.
export async function sessionEmail(cookie: string | undefined) {
  if (!cookie) return null;
  const [email, expires, mac] = cookie.split("|");
  if (!mac || Number(expires) < Date.now()) return null;
  const expected = Buffer.from(await sign(`${email}|${expires}`));
  if (expected.length !== mac.length || !timingSafeEqual(expected, Buffer.from(mac))) return null;
  const rows = await db("SELECT 1 FROM enerzen_accounts WHERE email = $1 AND status = 'approved'", [email]);
  return rows.length ? email : null;
}
