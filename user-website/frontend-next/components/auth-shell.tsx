import Image from "next/image"
import Link from "next/link"
import type React from "react"

export function AuthShell({
  children,
  eyebrow = "Secure access",
  heading = "The workspace where your team ships faster, together.",
  blurb = "End-to-end encrypted. SOC 2 Type II compliant. Built for teams that move fast without breaking trust.",
}: {
  children: React.ReactNode
  eyebrow?: string
  heading?: string
  blurb?: string
}) {
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
          <Link href="/" className="flex items-center gap-2.5">
            <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
              <span className="size-2.5 rounded-full bg-primary-foreground" />
            </span>
            <span className="font-mono text-sm tracking-widest uppercase">
              Aurora
            </span>
          </Link>

          <div className="max-w-md">
            <p className="font-mono text-xs tracking-widest text-primary uppercase">
              {eyebrow}
            </p>
            <h2 className="mt-4 text-2xl font-semibold leading-snug text-balance">
              {heading}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              {blurb}
            </p>
          </div>
        </div>
      </section>

      {/* Content panel */}
      <section className="relative flex w-full items-center justify-center px-6 py-12 lg:w-1/2">
        {/* Mobile brand mark */}
        <Link
          href="/"
          className="absolute top-6 left-6 flex items-center gap-2.5 lg:hidden"
        >
          <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
            <span className="size-2.5 rounded-full bg-primary-foreground" />
          </span>
          <span className="font-mono text-sm tracking-widest uppercase">
            Aurora
          </span>
        </Link>
        {children}
      </section>
    </main>
  )
}
