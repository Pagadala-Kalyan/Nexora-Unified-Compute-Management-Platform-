import Link from "next/link"
import { ArrowLeft } from "lucide-react"
import { AuthShell } from "@/components/auth-shell"
import { DeveloperSignupForm } from "@/components/developer-signup-form"

export const metadata = {
  title: "Aurora — Developer signup",
  description: "Create your developer account",
}

export default function DeveloperSignupPage() {
  return (
    <AuthShell
      eyebrow="Developer"
      heading="Build and deploy on the Aurora network."
      blurb="Access on-demand compute contributed by providers around the world."
    >
      <div className="w-full max-w-sm">
      <Link
        href="/signup"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to role
      </Link>

      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-balance">Create your developer account</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Just the basics to get you building on the network.
        </p>
      </div>

      <DeveloperSignupForm />

      <p className="mt-8 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
      </div>
    </AuthShell>
  )
}
