import Link from "next/link"
import { ArrowRight, Code2, Server } from "lucide-react"
import { AuthShell } from "@/components/auth-shell"

export const metadata = {
  title: "Aurora — Create account",
  description: "Choose how you want to use Aurora",
}

const roles = [
  {
    href: "/signup/developer",
    icon: Code2,
    title: "Developer",
    description: "Build and deploy apps. Consume compute from the network.",
  },
  {
    href: "/signup/provider",
    icon: Server,
    title: "Provider",
    description: "Contribute your devices and share spare RAM and compute.",
  },
]

export default function SignupRolePage() {
  return (
    <AuthShell
      eyebrow="Create account"
      heading="Join the network. Build or provide compute."
      blurb="One account, two ways in. Ship apps as a developer, or share your spare compute as a provider."
    >
      <div className="w-full max-w-sm">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-balance">How will you use Aurora?</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Pick a role to continue. You can change this later in settings.
        </p>
      </div>
      <div className="flex flex-col gap-4">
        {roles.map((role) => (
          <Link
            key={role.href}
            href={role.href}
            className="group flex items-center gap-4 rounded-xl border border-border bg-secondary/40 p-5 transition-colors hover:border-primary/60 hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <role.icon className="size-5" aria-hidden="true" />
            </span>
            <span className="flex flex-col">
              <span className="text-sm font-semibold text-foreground">{role.title}</span>
              <span className="text-sm leading-relaxed text-muted-foreground">{role.description}</span>
            </span>
            <ArrowRight
              className="ml-auto size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
              aria-hidden="true"
            />
          </Link>
        ))}
      </div>

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
