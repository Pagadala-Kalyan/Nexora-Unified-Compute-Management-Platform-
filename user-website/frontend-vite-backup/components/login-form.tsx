"use client"

import type React from "react"
import { useState } from "react"
import Link from "next/link"
import { ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"

export function LoginForm() {
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    // Simulate an auth request
    setTimeout(() => setLoading(false), 1400)
  }

  return (
    <div className="w-full max-w-sm">
      <div className="mb-8">
        <span className="inline-block rounded-full border border-border bg-secondary px-3 py-1 font-mono text-xs tracking-widest text-muted-foreground uppercase">
          Aurora ID
        </span>
        <h1 className="mt-6 text-3xl font-semibold tracking-tight text-balance">
          Welcome back
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Sign in to continue to your workspace.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <label
            htmlFor="email"
            className="font-mono text-xs tracking-wider text-muted-foreground uppercase"
          >
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            placeholder="you@company.com"
            className="h-11 rounded-lg border border-input bg-card px-3.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
          />
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label
              htmlFor="password"
              className="font-mono text-xs tracking-wider text-muted-foreground uppercase"
            >
              Password
            </label>
            <a
              href="#"
              className="text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              Forgot?
            </a>
          </div>
          <div className="relative">
            <input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              placeholder="••••••••••••"
              className="h-11 w-full rounded-lg border border-input bg-card px-3.5 pr-11 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
            >
              {showPassword ? (
                <EyeOff className="size-4" />
              ) : (
                <Eye className="size-4" />
              )}
            </button>
          </div>
        </div>

        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground select-none">
          <input
            type="checkbox"
            name="remember"
            className="size-4 rounded border-input bg-card accent-primary"
          />
          Keep me signed in
        </label>

        <Button
          type="submit"
          size="lg"
          disabled={loading}
          className="mt-1 h-11 w-full text-sm font-medium"
        >
          {loading ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Signing in…
            </>
          ) : (
            <>
              Sign in
              <ArrowRight className="size-4" />
            </>
          )}
        </Button>
      </form>

      <div className="my-7 flex items-center gap-4">
        <span className="h-px flex-1 bg-border" />
        <span className="font-mono text-[0.7rem] tracking-widest text-muted-foreground uppercase">
          or
        </span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Button variant="outline" size="lg" className="h-11">
          <GoogleIcon className="size-4" />
          Google
        </Button>
        <Button variant="outline" size="lg" className="h-11">
          <GitHubIcon className="size-4" />
          GitHub
        </Button>
      </div>

      <p className="mt-8 text-center text-sm text-muted-foreground">
        {"Don't have an account? "}
        <Link
          href="/signup"
          className="font-medium text-foreground underline-offset-4 transition-colors hover:text-primary hover:underline"
        >
          Create one
        </Link>
      </p>
    </div>
  )
}

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M12 11v2.8h4c-.2 1-1.3 3-4 3-2.4 0-4.3-2-4.3-4.5S9.6 7.8 12 7.8c1.4 0 2.3.6 2.8 1.1l1.9-1.8C15.5 6 13.9 5.3 12 5.3 8.3 5.3 5.3 8.3 5.3 12s3 6.7 6.7 6.7c3.9 0 6.4-2.7 6.4-6.5 0-.4 0-.8-.1-1.2H12Z"
      />
    </svg>
  )
}

function GitHubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M12 2C6.5 2 2 6.6 2 12.3c0 4.5 2.9 8.3 6.8 9.7.5.1.7-.2.7-.5v-1.7c-2.8.6-3.4-1.4-3.4-1.4-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.6 2.4 1.1 3 .9.1-.7.4-1.1.6-1.4-2.2-.3-4.6-1.1-4.6-5 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.7 1 .8-.2 1.6-.3 2.5-.3.8 0 1.7.1 2.5.3 1.9-1.3 2.7-1 2.7-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.9-2.3 4.7-4.6 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5 3.9-1.4 6.8-5.2 6.8-9.7C22 6.6 17.5 2 12 2Z"
      />
    </svg>
  )
}
