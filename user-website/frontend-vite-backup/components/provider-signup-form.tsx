"use client"

import { type FormEvent, useState } from "react"
import { Loader2, Plus, Trash2, Cpu } from "lucide-react"
import { Field } from "@/components/field"

interface Device {
  id: number
  name: string
  ram: string
}

let nextId = 2

export function ProviderSignupForm() {
  const [loading, setLoading] = useState(false)
  const [devices, setDevices] = useState<Device[]>([{ id: 1, name: "", ram: "" }])

  const totalRam = devices.reduce((sum, d) => sum + (Number.parseFloat(d.ram) || 0), 0)

  function updateDevice(id: number, patch: Partial<Device>) {
    setDevices((prev) => prev.map((d) => (d.id === id ? { ...d, ...patch } : d)))
  }

  function addDevice() {
    setDevices((prev) => [...prev, { id: nextId++, name: "", ram: "" }])
  }

  function removeDevice(id: number) {
    setDevices((prev) => (prev.length > 1 ? prev.filter((d) => d.id !== id) : prev))
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setTimeout(() => setLoading(false), 1200)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <Field id="prov-name" name="name" label="Full name" placeholder="Grace Hopper" autoComplete="name" required />
      <Field
        id="prov-email"
        name="email"
        type="email"
        label="Email"
        placeholder="you@example.com"
        autoComplete="email"
        required
      />
      <Field
        id="prov-password"
        name="password"
        type="password"
        label="Password"
        placeholder="At least 8 characters"
        autoComplete="new-password"
        minLength={8}
        required
      />

      <div className="mt-2 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-xs uppercase tracking-wider text-muted-foreground">Your devices</h2>
          <span className="flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
            <Cpu className="size-3.5" aria-hidden="true" />
            {totalRam.toFixed(1)} GB available
          </span>
        </div>

        <div className="flex flex-col gap-3">
          {devices.map((device, index) => (
            <div key={device.id} className="rounded-xl border border-border bg-secondary/30 p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-xs font-medium text-foreground">Device {index + 1}</span>
                <button
                  type="button"
                  onClick={() => removeDevice(device.id)}
                  disabled={devices.length === 1}
                  className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-muted-foreground"
                  aria-label={`Remove device ${index + 1}`}
                >
                  <Trash2 className="size-4" aria-hidden="true" />
                </button>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field
                  id={`device-name-${device.id}`}
                  label="Device name"
                  placeholder="Home workstation"
                  value={device.name}
                  onChange={(e) => updateDevice(device.id, { name: e.target.value })}
                  required
                />
                <Field
                  id={`device-ram-${device.id}`}
                  type="number"
                  min="0.5"
                  step="0.5"
                  label="Free RAM (GB)"
                  placeholder="16"
                  value={device.ram}
                  onChange={(e) => updateDevice(device.id, { ram: e.target.value })}
                  required
                />
              </div>
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={addDevice}
          className="flex h-11 items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm font-medium text-muted-foreground transition-colors hover:border-primary/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Plus className="size-4" aria-hidden="true" />
          Add another device
        </button>
      </div>

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
          "Create provider account"
        )}
      </button>
    </form>
  )
}
