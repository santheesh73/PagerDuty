import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ShieldCheck, ShieldAlert, Laptop } from "lucide-react";
import { ApiError } from "@/api/client";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader, PageHeader } from "@/components/Card";
import { Field, Input } from "@/components/Field";
import { ErrorState, SkeletonRows } from "@/components/States";
import { useMfaStatus } from "@/features/auth/hooks";
import { useDocumentTitle } from "@/lib/hooks";
import {
  useChangePassword,
  useMfaConfirm,
  useMfaDisable,
  useMfaSetup,
  useRegenerateBackupCodes,
  useRevokeOtherSessions,
  useRevokeSession,
  useSessions,
} from "./hooks";

function errorOf(error: unknown): ApiError | null {
  return error instanceof ApiError ? error : null;
}

export function SecurityPage() {
  useDocumentTitle("Security");
  const status = useMfaStatus();
  return (
    <>
      <PageHeader
        title="Security"
        description="Two-factor authentication, your password and where you're signed in."
      />
      {status.data?.enforced && !status.data.enabled && (
        <div
          role="alert"
          className="mb-6 rounded-xl border border-critical/40 bg-critical-soft px-4 py-3 text-sm text-critical-fg"
        >
          Team admins must set up two-factor authentication before they can use Pulse.
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <MfaCard />
        <PasswordCard />
        <SessionsCard />
      </div>
    </>
  );
}

function BackupCodeList({ codes }: { codes: string[] }) {
  return (
    <div className="space-y-2">
      <p className="text-sm">
        Save these backup codes somewhere safe. Each works once if you lose your phone.{" "}
        <strong>They won't be shown again.</strong>
      </p>
      <ul className="grid grid-cols-2 gap-1 rounded-lg bg-surface-2 p-3 font-mono text-sm">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => void navigator.clipboard.writeText(codes.join("\n"))}
      >
        Copy all
      </Button>
    </div>
  );
}

function MfaCard() {
  const status = useMfaStatus();
  const setup = useMfaSetup();
  const confirm = useMfaConfirm();
  const disable = useMfaDisable();
  const regenerate = useRegenerateBackupCodes();
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);

  if (status.isPending)
    return (
      <Card className="p-4">
        <SkeletonRows rows={3} />
      </Card>
    );
  if (status.error)
    return <ErrorState error={status.error} onRetry={() => void status.refetch()} />;
  const { enabled, enforced, backup_codes_remaining } = status.data;

  return (
    <Card>
      <CardHeader
        title="Two-factor authentication"
        description="A code from an authenticator app (1Password, Google Authenticator, Authy...) at every sign-in."
        action={
          enabled ? (
            <Badge tone="good">
              <ShieldCheck className="size-3.5" aria-hidden /> On
            </Badge>
          ) : (
            <Badge tone="neutral">
              <ShieldAlert className="size-3.5" aria-hidden /> Off
            </Badge>
          )
        }
      />
      <div className="space-y-4 p-4">
        {codes && <BackupCodeList codes={codes} />}

        {!enabled && !setup.data && (
          <Button variant="primary" loading={setup.isPending} onClick={() => setup.mutate()}>
            Set up two-factor authentication
          </Button>
        )}

        {!enabled && setup.data && (
          <form
            className="space-y-3"
            noValidate
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              confirm.mutate(code.trim(), {
                onSuccess: (result) => {
                  setCodes(result.backup_codes);
                  setCode("");
                  toast.success("Two-factor authentication is on");
                },
              });
            }}
          >
            <p className="text-sm">
              In your authenticator app, add an account with this key (or open the link on your
              phone):
            </p>
            <code className="block rounded-lg bg-surface-2 px-3 py-2 font-mono text-sm break-all">
              {setup.data.secret}
            </code>
            <a href={setup.data.otpauth_uri} className="text-xs text-accent hover:underline">
              Open in authenticator app
            </a>
            <Field
              label="Then enter the 6-digit code it shows"
              error={errorOf(confirm.error)?.fieldError("code")}
            >
              {(props) => (
                <Input
                  {...props}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              )}
            </Field>
            <Button type="submit" variant="primary" loading={confirm.isPending}>
              Turn on
            </Button>
          </form>
        )}

        {enabled && (
          <>
            <p className="text-sm text-muted">
              {backup_codes_remaining} unused backup code{backup_codes_remaining === 1 ? "" : "s"}{" "}
              left.
            </p>
            <form className="space-y-3" noValidate onSubmit={(e: FormEvent) => e.preventDefault()}>
              <Field
                label="Code from your authenticator app"
                error={errorOf(regenerate.error ?? disable.error)?.message}
              >
                {(props) => (
                  <Input
                    {...props}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                )}
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  loading={regenerate.isPending}
                  onClick={() =>
                    regenerate.mutate(code.trim(), {
                      onSuccess: (r) => {
                        setCodes(r.backup_codes);
                        setCode("");
                      },
                    })
                  }
                >
                  New backup codes
                </Button>
              </div>
              {!enforced && (
                <div className="space-y-3 border-t border-border pt-3">
                  <Field label="Password (to turn it off)">
                    {(props) => (
                      <Input
                        {...props}
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                      />
                    )}
                  </Field>
                  <Button
                    variant="danger"
                    loading={disable.isPending}
                    onClick={() =>
                      disable.mutate(
                        { password, code: code.trim() },
                        {
                          onSuccess: () => {
                            setCode("");
                            setPassword("");
                            setCodes(null);
                            setup.reset();
                            toast.success("Two-factor authentication is off");
                          },
                        },
                      )
                    }
                  >
                    Turn off
                  </Button>
                </div>
              )}
              {enforced && (
                <p className="text-xs text-subtle">
                  Required for team admins, so it can't be turned off.
                </p>
              )}
            </form>
          </>
        )}
      </div>
    </Card>
  );
}

function PasswordCard() {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const error = errorOf(change.error);
  return (
    <Card>
      <CardHeader title="Password" description="Changing it signs out every other session." />
      <form
        className="space-y-3 p-4"
        noValidate
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          change.mutate(
            { current_password: current, new_password: next },
            {
              onSuccess: () => {
                setCurrent("");
                setNext("");
                toast.success("Password changed");
              },
            },
          );
        }}
      >
        <Field label="Current password" error={error?.fieldError("current_password")}>
          {(props) => (
            <Input
              {...props}
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          )}
        </Field>
        <Field
          label="New password"
          hint="At least 12 characters."
          error={error?.fieldError("new_password")}
        >
          {(props) => (
            <Input
              {...props}
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" variant="primary" loading={change.isPending}>
          Change password
        </Button>
      </form>
    </Card>
  );
}

function SessionsCard() {
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const revokeOthers = useRevokeOtherSessions();
  return (
    <Card className="lg:col-span-2">
      <CardHeader
        title="Where you're signed in"
        action={
          <Button size="sm" loading={revokeOthers.isPending} onClick={() => revokeOthers.mutate()}>
            Sign out everywhere else
          </Button>
        }
      />
      {sessions.isPending ? (
        <div className="p-4">
          <SkeletonRows rows={2} />
        </div>
      ) : sessions.error ? (
        <ErrorState error={sessions.error} onRetry={() => void sessions.refetch()} />
      ) : (
        <ul className="divide-y divide-border">
          {sessions.data.map((s) => (
            <li key={s.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <Laptop className="size-4 text-muted" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate">{s.user_agent || "Unknown device"}</p>
                <p className="text-xs text-muted">
                  {s.ip ?? "unknown address"} · since {new Date(s.created_at).toLocaleString()}
                </p>
              </div>
              {s.current ? (
                <Badge tone="accent">This device</Badge>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => revoke.mutate(s.id)}>
                  Sign out
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
