import Link from "next/link"
import { ArrowLeft } from "lucide-react"
import { AuthShell } from "@/components/auth-shell"
import { ProviderSignupForm } from "@/components/provider-signup-form"

export const metadata = {
  title: "Aurora — Provider signup",
  description: "Create your provider account and register your devices",
}

export default function ProviderSignupPage() {
  return (
    <AuthShell
      eyebrow="Provider"
      heading="Share your compute. Earn from idle machines."
      blurb="Register your devices and the RAM you can spare. Aurora routes workloads to you automatically."
    >
      <div className="w-full max-w-md">
      <Link
        href="/signup"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to role
      </Link>

      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-balance">Register as a provider</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Add your devices and how much RAM you can share with the network.
        </p>
      </div>

      <ProviderSignupForm />

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
