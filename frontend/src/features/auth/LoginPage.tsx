import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Field, Input } from "@/components/Field";
import { Logo } from "@/components/Logo";
import { useDocumentTitle } from "@/lib/hooks";
import { isMfaChallenge, useLogin, useLoginMfa, useMe } from "./hooks";

const SHOW_DEMO = import.meta.env.DEV || import.meta.env.VITE_SHOW_DEMO_CREDENTIALS === "true";
const DEMO_ACCOUNTS = [
  { email: "responder@demo.local", role: "Responder — on call for Payments" },
  { email: "admin@demo.local", role: "Team admin" },
];

function safeNext(raw: string | null): string {
  // Only same-app paths: never redirect to another origin after login.
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

export function LoginPage() {
  useDocumentTitle("Sign in");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const next = safeNext(params.get("next"));
  // /admin/ is Django's, not a route in this app: leave the SPA to get there.
  const go = () =>
    next.startsWith("/admin/") ? window.location.assign(next) : navigate(next, { replace: true });

  if (me && !next.startsWith("/admin/")) return <Navigate to={next} replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate(
      { email, password },
      { onSuccess: (result) => (isMfaChallenge(result) ? setNeedsCode(true) : go()) },
    );
  };
  const error = login.error instanceof ApiError ? login.error : null;

  if (needsCode) {
    return (
      <Shell title="Two-factor authentication" subtitle="Enter the 6-digit code from your app.">
        <CodeForm
          onDone={go}
          onRestart={() => {
            setNeedsCode(false);
            setPassword("");
          }}
        />
      </Shell>
    );
  }

  return (
    <main className="grid min-h-screen place-items-center bg-bg px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="size-10" />
          <h1 className="mt-4 text-xl font-semibold tracking-tight">Sign in to Pulse</h1>
          <p className="mt-1 text-muted">Incident response, without the noise.</p>
        </div>
        <form
          onSubmit={submit}
          className="space-y-4 rounded-2xl border border-border bg-surface p-6 shadow-card"
          noValidate
        >
          <Field label="Email">
            {(props) => (
              <Input
                {...props}
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
              />
            )}
          </Field>
          <Field label="Password" error={error?.message}>
            {(props) => (
              <Input
                {...props}
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" variant="primary" className="w-full" loading={login.isPending}>
            Sign in
          </Button>
          <p className="text-center text-xs">
            <Link to="/forgot-password" className="text-accent hover:underline">
              Forgot your password?
            </Link>
          </p>
        </form>

        {SHOW_DEMO && (
          <div className="mt-4 rounded-xl border border-border bg-surface-2/60 p-4 text-sm">
            <p className="font-medium">
              Demo accounts · password <code className="font-mono">demo1234</code>
            </p>
            <ul className="mt-2 space-y-1.5">
              {DEMO_ACCOUNTS.map((account) => (
                <li key={account.email} className="flex items-center justify-between gap-2">
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-xs">{account.email}</span>
                    <span className="text-xs text-muted">{account.role}</span>
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setEmail(account.email);
                      setPassword("demo1234");
                    }}
                  >
                    Use
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </main>
  );
}

function Shell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <main className="grid min-h-screen place-items-center bg-bg px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="size-10" />
          <h1 className="mt-4 text-xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-muted">{subtitle}</p>
        </div>
        <div className="space-y-4 rounded-2xl border border-border bg-surface p-6 shadow-card">
          {children}
        </div>
      </div>
    </main>
  );
}

export { Shell as AuthShell };

function CodeForm({ onDone, onRestart }: { onDone: () => void; onRestart: () => void }) {
  const verify = useLoginMfa();
  const [code, setCode] = useState("");
  const error = verify.error instanceof ApiError ? verify.error : null;
  const expired = error?.code === "mfa_session_expired";

  return (
    <form
      className="space-y-4"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        verify.mutate(code.trim(), { onSuccess: onDone });
      }}
    >
      <Field
        label="Authentication code"
        hint="Lost your phone? Enter one of your backup codes instead."
        error={error?.message}
      >
        {(props) => (
          <Input
            {...props}
            inputMode="text"
            autoComplete="one-time-code"
            autoFocus
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        )}
      </Field>
      {expired ? (
        <Button type="button" variant="primary" className="w-full" onClick={onRestart}>
          Sign in again
        </Button>
      ) : (
        <Button type="submit" variant="primary" className="w-full" loading={verify.isPending}>
          Verify
        </Button>
      )}
      <button
        type="button"
        className="w-full text-center text-xs text-muted hover:underline"
        onClick={onRestart}
      >
        Use a different account
      </button>
    </form>
  );
}
