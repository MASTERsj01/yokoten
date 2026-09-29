import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <section className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-4 py-24">
      <h1 className="text-4xl font-semibold tracking-tight">Spread every lesson learned across every team.</h1>
      <p className="text-lg text-muted-foreground">
        Yokoten answers engineering questions from past 8D reports, FMEAs, test reports and design reviews — with
        citations to the exact page.
      </p>
      <div>
        <Button asChild>
          <Link href="/chat">Open the copilot</Link>
        </Button>
      </div>
    </section>
  );
}
