import type { InputHTMLAttributes } from "react"

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
}

export function Field({ label, hint, id, className, ...props }: FieldProps) {
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={id}
        className="font-mono text-xs uppercase tracking-wider text-muted-foreground"
      >
        {label}
      </label>
      <input
        id={id}
        className="h-11 rounded-lg border border-input bg-secondary/40 px-3.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-primary/60 focus:bg-secondary focus:ring-2 focus:ring-ring/40 disabled:opacity-50"
        {...props}
      />
      {hint ? <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p> : null}
    </div>
  )
}
