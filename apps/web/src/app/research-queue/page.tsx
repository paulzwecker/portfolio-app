import { redirect } from "next/navigation";

export default function ResearchQueueCompatibilityRoute() {
  redirect("/research?view=queue");
}
