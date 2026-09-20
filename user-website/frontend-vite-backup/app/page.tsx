import Image from "next/image"
import { LoginForm } from "@/components/login-form"

export default function LoginPage() {
  return (
    <main className="flex min-h-svh w-full">
      {/* Brand / atmosphere panel */}
      <section className="relative hidden w-1/2 overflow-hidden lg:block">
        <Image
          src="/aurora-panel.png"
          alt=""
          fill
          priority
          sizes="50vw"
          className="object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-background/70 via-background/10 to-transparent" />

        <div className="relative flex h-full flex-col justify-between p-10">
          <div className="flex items-center gap-2.5">
            <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
              <span className="size-2.5 rounded-full bg-primary-foreground" />
            </span>
            <span className="font-mono text-sm tracking-widest uppercase">
              Aurora
            </span>
          </div>

          <div className="max-w-md">
            <p className="font-mono text-xs tracking-widest text-primary uppercase">
              Secure access
            </p>
            <h2 className="mt-4 text-2xl font-semibold leading-snug text-balance">
              The workspace where your team ships faster, together.
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              End-to-end encrypted. SOC 2 Type II compliant. Built for teams
              that move fast without breaking trust.
            </p>
          </div>
        </div>
      </section>

      {/* Form panel */}
      <section className="flex w-full items-center justify-center px-6 py-12 lg:w-1/2">
        {/* Mobile brand mark */}
        <div className="absolute top-6 left-6 flex items-center gap-2.5 lg:hidden">
          <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
            <span className="size-2.5 rounded-full bg-primary-foreground" />
          </span>
          <span className="font-mono text-sm tracking-widest uppercase">
            Aurora
          </span>
        </div>
        <LoginForm />
      </section>
    </main>
  )
}
