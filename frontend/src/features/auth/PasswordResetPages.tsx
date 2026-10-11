import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Field, Input } from "@/components/Field";
import { useDocumentTitle } from "@/lib/hooks";
import { usePasswordResetConfirm, usePasswordResetRequest } from "./hooks";
import { AuthShell } from "./LoginPage";

export function ForgotPasswordPage() {
  useDocumentTitle("Reset your password");
  const request = usePasswordResetRequest();
  const [email, setEmail] = useState("");

  if (request.isSuccess) {
    return (
      <AuthShell
        title="Check your email"
        subtitle="If an account uses that address, a link is on its way."
      >
        <p className="text-sm text-muted">
          The link works once and expires in an hour. It can take a minute to arrive.
        </p>
        <Link to="/login" className="block text-center text-sm text-accent hover:underline">
          Back to sign in
        </Link>
      </AuthShell>
    );
  }
  return (
    <AuthShell title="Reset your password" subtitle="We'll email you a link to choose a new one.">
      <form
        className="space-y-4"
        noValidate
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          request.mutate(email);
        }}
      >
        <Field
          label="Email"
          error={request.error instanceof ApiError ? request.error.message : undefined}
        >
          {(props) => (
            <Input
              {...props}
              type="email"
              autoComplete="username"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" variant="primary" className="w-full" loading={request.isPending}>
          Send reset link
        </Button>
        <Link to="/login" className="block text-center text-xs text-muted hover:underline">
          Back to sign in
        </Link>
      </form>
    </AuthShell>
  );
}

export function ResetPasswordPage() {
  useDocumentTitle("Choose a new password");
  const [params] = useSearchParams();
  const confirm = usePasswordResetConfirm();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const error = confirm.error instanceof ApiError ? confirm.error : null;
  const mismatch = again.length > 0 && again !== password;

  if (confirm.isSuccess) {
    return (
      <AuthShell
        title="Password changed"
        subtitle="Every session that used the old password was signed out."
      >
        <Link to="/login" className="block text-center text-sm text-accent hover:underline">
          Sign in
        </Link>
      </AuthShell>
    );
  }
  return (
    <AuthShell
      title="Choose a new password"
      subtitle="At least 12 characters. A few words make a good one."
    >
      <form
        className="space-y-4"
        noValidate
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          if (!mismatch) confirm.mutate({ uid, token, new_password: password });
        }}
      >
        {error?.code === "invalid_token" && (
          <p className="rounded-lg bg-critical-soft px-3 py-2 text-sm text-critical-fg">
            This link is invalid or has expired.{" "}
            <Link to="/forgot-password" className="underline">
              Request a new one
            </Link>
            .
          </p>
        )}
        <Field label="New password" error={error?.fieldError("new_password")}>
          {(props) => (
            <Input
              {...props}
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <Field label="Repeat it" error={mismatch ? "The two passwords don't match." : undefined}>
          {(props) => (
            <Input
              {...props}
              type="password"
              autoComplete="new-password"
              required
              value={again}
              onChange={(e) => setAgain(e.target.value)}
            />
          )}
        </Field>
        <Button
          type="submit"
          variant="primary"
          className="w-full"
          loading={confirm.isPending}
          disabled={!uid || !token || mismatch || password.length < 12}
        >
          Set password
        </Button>
      </form>
    </AuthShell>
  );
}
