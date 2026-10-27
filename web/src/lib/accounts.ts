// Who may use the site. Accounts live in one JSON file on the server (ACCOUNTS_DIR,
// a compose volume), since a handful of invited people don't need a database.
import { createHmac, randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export type Account = {
  email: string;
  name: string;
  note: string;
  hash: string; // salt:scrypt hex
  status: "pending" | "approved";
  requestedAt: string;
};

export const SESSION_COOKIE = "enerzen_session";
const SESSION_DAYS = 30;
const dir = process.env.ACCOUNTS_DIR ?? join(process.cwd(), ".accounts");
const file = join(dir, "accounts.json");

const admins = () =>
  (process.env.ADMIN_EMAILS ?? "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
export const isAdmin = (email: string) => admins().includes(email);

export function loadAccounts(): Account[] {
  return existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : [];
}

function saveAccounts(accounts: Account[]) {
  mkdirSync(dir, { recursive: true });
  writeFileSync(`${file}.tmp`, JSON.stringify(accounts, null, 2));
  renameSync(`${file}.tmp`, file); // a crash mid-write never leaves half a file
}

function hashPassword(password: string) {
  const salt = randomBytes(16).toString("hex");
  return `${salt}:${scryptSync(password, salt, 64).toString("hex")}`;
}

function passwordMatches(password: string, stored: string) {
  const [salt, hex] = stored.split(":");
  return timingSafeEqual(scryptSync(password, salt, 64), Buffer.from(hex, "hex"));
}

// Returns an error to show, or null. Admins (ADMIN_EMAILS) are approved on request.
export function requestAccount(email: string, name: string, note: string, password: string) {
  const accounts = loadAccounts();
  if (accounts.some((a) => a.email === email)) return "That email has already asked for access.";
  accounts.push({
    email, name, note,
    hash: hashPassword(password),
    status: isAdmin(email) ? "approved" : "pending",
    requestedAt: new Date().toISOString(),
  });
  saveAccounts(accounts);
  return null;
}

export function checkLogin(email: string, password: string) {
  const account = loadAccounts().find((a) => a.email === email);
  if (!account || !passwordMatches(password, account.hash)) return "Wrong email or password.";
  if (account.status !== "approved") return "Your request is waiting for approval.";
  return null;
}

export function setStatus(email: string, status: "approved" | "removed") {
  const accounts = loadAccounts();
  saveAccounts(
    status === "removed"
      ? accounts.filter((a) => a.email !== email)
      : accounts.map((a) => (a.email === email ? { ...a, status } : a)),
  );
}

// Kept beside the accounts so sessions survive rebuilds without another setting.
function secret() {
  const path = join(dir, "session-secret");
  if (!existsSync(path)) {
    mkdirSync(dir, { recursive: true });
    writeFileSync(path, randomBytes(32).toString("hex"), { flag: "wx" });
  }
  return readFileSync(path, "utf8");
}

const sign = (value: string) => createHmac("sha256", secret()).update(value).digest("hex");

export function makeSession(email: string) {
  const value = `${email}|${Date.now() + SESSION_DAYS * 86_400_000}`;
  return { value: `${value}|${sign(value)}`, maxAge: SESSION_DAYS * 86_400 };
}

// The signed-in email, only while the cookie is genuine, unexpired and the account
// still approved, so removing someone signs them out on their next request.
export function sessionEmail(cookie: string | undefined) {
  if (!cookie) return null;
  const [email, expires, mac] = cookie.split("|");
  if (!mac || Number(expires) < Date.now()) return null;
  const expected = Buffer.from(sign(`${email}|${expires}`));
  if (expected.length !== mac.length || !timingSafeEqual(expected, Buffer.from(mac))) return null;
  return loadAccounts().some((a) => a.email === email && a.status === "approved") ? email : null;
}
