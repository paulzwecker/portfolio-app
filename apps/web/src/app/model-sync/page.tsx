import { redirect } from "next/navigation";

/** Keep the legacy entry point pointed at the consolidated proposal review. */
export default function ModelSyncCompatibilityRoute() {
  redirect("/research?view=reviews");
}
