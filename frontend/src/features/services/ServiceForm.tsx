import { useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "@/api/client";
import type { Service } from "@/api/types";
import { Button } from "@/components/Button";
import { Dialog } from "@/components/Dialog";
import { Field, Input, Select, Textarea } from "@/components/Field";
import { adminTeams, useMe } from "@/features/auth/hooks";
import { usePolicies } from "@/features/policies/hooks";
import { useSaveService } from "./hooks";

interface Props {
  open: boolean;
  onClose: () => void;
  service?: Service;
}

/** Mounts the form only while open, so each opening starts from fresh state. */
export function ServiceFormDialog(props: Props) {
  return props.open ? <ServiceForm {...props} /> : null;
}

function ServiceForm({ open, onClose, service }: Props) {
  const { data: me } = useMe();
  const teams = adminTeams(me);
  const policies = usePolicies();
  const save = useSaveService(service?.id);
  const navigate = useNavigate();
  const [form, setForm] = useState(() => ({
    team: String(service?.team ?? teams[0]?.id ?? ""),
    name: service?.name ?? "",
    description: service?.description ?? "",
    escalation_policy: String(service?.escalation_policy ?? ""),
  }));

  const teamPolicies = policies.data?.filter((p) => String(p.team) === form.team) ?? [];
  const error = save.error instanceof ApiError ? save.error : null;

  const submit = () =>
    save.mutate(
      {
        team: Number(form.team),
        name: form.name.trim(),
        description: form.description,
        escalation_policy: Number(form.escalation_policy),
      },
      {
        onSuccess: (saved) => {
          onClose();
          if (!service) navigate(`/services/${saved.id}`);
        },
      },
    );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={service ? "Edit service" : "New service"}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!form.name.trim() || !form.escalation_policy}
            onClick={submit}
          >
            {service ? "Save" : "Create service"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {!service && (
          <Field label="Team" error={error?.fieldError("team")}>
            {(props) => (
              <Select
                {...props}
                value={form.team}
                onChange={(e) => setForm({ ...form, team: e.target.value, escalation_policy: "" })}
              >
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        <Field
          label="Name"
          error={error?.fieldError("name")}
          hint="Lowercase and dashes read well in pages, e.g. checkout-api."
        >
          {(props) => (
            <Input
              {...props}
              data-autofocus
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          )}
        </Field>
        <Field label="Description">
          {(props) => (
            <Textarea
              {...props}
              rows={2}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          )}
        </Field>
        <Field
          label="Escalation policy"
          error={error?.fieldError("escalation_policy")}
          hint={
            teamPolicies.length === 0
              ? "This team has no policies yet — create one first."
              : undefined
          }
        >
          {(props) => (
            <Select
              {...props}
              value={form.escalation_policy}
              onChange={(e) => setForm({ ...form, escalation_policy: e.target.value })}
            >
              <option value="">Choose a policy…</option>
              {teamPolicies.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {error && !error.fieldError("name") && !error.fieldError("escalation_policy") && (
          <p className="text-sm text-critical-fg" role="alert">
            {error.message}
          </p>
        )}
      </div>
    </Dialog>
  );
}
