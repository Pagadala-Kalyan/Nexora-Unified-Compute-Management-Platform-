const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"

export async function authenticate(endpoint: "/auth/login" | "/auth/register", email: string, password: string) {
  const response = await fetch(`${API_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  })
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.detail || "Authentication failed")
  localStorage.setItem("nexora_token", payload.access_token)
  return payload
}
