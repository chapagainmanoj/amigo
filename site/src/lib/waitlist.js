/**
 * The only network call the marketing page makes.
 *
 * Phase 1 posts to a hosted form provider named by VITE_WAITLIST_ENDPOINT. Phase 2 (a
 * Supabase-backed table behind POST /api/waitlist) replaces the body of submitWaitlist and
 * touches nothing else — see docs/landing-page-spec.md section 8.
 */

const CONFIG_ERROR = "Waitlist signup isn't configured yet."
const GENERIC_ERROR = "That didn't go through — try again in a moment."

// A provider that already holds this address answers 409 (or 422). That is a success for the
// person signing up, and telling them otherwise both confuses them and leaks whether an
// address is on the list.
const ALREADY_SUBSCRIBED = new Set([409, 422])

export function isWaitlistConfigured() {
  return Boolean(import.meta.env.VITE_WAITLIST_ENDPOINT?.trim())
}

export async function submitWaitlist(email) {
  const endpoint = import.meta.env.VITE_WAITLIST_ENDPOINT?.trim()

  if (!endpoint) {
    throw new Error(CONFIG_ERROR)
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 10000)

  let response
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ email }),
      signal: controller.signal,
    })
  } catch (err) {
    throw new Error(GENERIC_ERROR, { cause: err })
  } finally {
    clearTimeout(timeoutId)
  }

  if (response.ok || ALREADY_SUBSCRIBED.has(response.status)) {
    return { ok: true }
  }

  throw new Error(GENERIC_ERROR)
}
