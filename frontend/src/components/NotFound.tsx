import { Link } from "react-router";
import { Button } from "./Button";
import { EmptyState } from "./States";

export function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Link to="/">
          <Button variant="primary">Go to the dashboard</Button>
        </Link>
      }
    >
      That link doesn't lead anywhere in Pulse.
    </EmptyState>
  );
}
