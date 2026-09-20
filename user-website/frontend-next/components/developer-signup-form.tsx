"use client"

import { type FormEvent, useState } from "react"
import { Loader2 } from "lucide-react"
import { Field } from "@/components/field"
import { authenticate } from "@/lib/api"

export function DeveloperSignupForm() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setError("")
    const form = new FormData(e.currentTarget)
    try { await authenticate("/auth/register", String(form.get("email")), String(form.get("password"))); window.location.assign("/dashboard") }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to create account") }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      {error && <p className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      <Field id="dev-name" name="name" label="Full name" placeholder="Ada Lovelace" autoComplete="name" required />
      <Field
        id="dev-email"
        name="email"
        type="email"
        label="Work email"
        placeholder="you@company.com"
        autoComplete="email"
        required
      />
      <Field
        id="dev-password"
        name="password"
        type="password"
        label="Password"
        placeholder="At least 8 characters"
        autoComplete="new-password"
        minLength={8}
        required
      />

      <button
        type="submit"
        disabled={loading}
        className="mt-1 flex h-11 items-center justify-center gap-2 rounded-lg bg-primary text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
      >
        {loading ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            Creating account
          </>
        ) : (
          "Create developer account"
        )}
      </button>
    </form>
  )
}
