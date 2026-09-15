/**
 * The only network call the marketing page makes.
 *
 * Phase 1 posts to the Loops form endpoint named by VITE_WAITLIST_ENDPOINT. Phase 2 (a
 * Supabase-backed table behind POST /api/waitlist) replaces the body of submitWaitlist and
 * touches nothing else — see docs/landing-page-spec.md section 8.
 *
 * The messages a visitor sees live in content/shared.jsx with the rest of the copy; only the
 * behaviour is here.
 */

import { WAITLIST } from '../content/shared'

const { unconfigured: CONFIG_ERROR, network: GENERIC_ERROR } = WAITLIST.errors

// Providers disagree on what to call the field: Loops and Formspark take `email`, Buttondown's
// API takes `email_address`. One env var beats editing this file if the provider ever changes.
const FIELD = import.meta.env.VITE_WAITLIST_FIELD?.trim() || 'email'

const endpointOf = () => import.meta.env.VITE_WAITLIST_ENDPOINT?.trim()

export function isWaitlistConfigured() {
  return Boolean(endpointOf())
}

// With no endpoint, a production build shows the honest fallback — but hiding the form in `npm run
// dev` too meant the page's primary CTA was invisible to the person building it. In dev the form
// renders and submits to nothing, labelled so it is never mistaken for a working signup.
export function isWaitlistPreview() {
  return !endpointOf() && import.meta.env.DEV
}

export async function submitWaitlist(email) {
  const endpoint = endpointOf()

  if (!endpoint) {
    if (import.meta.env.DEV) {
      console.warn(`[waitlist] preview only — "${email}" was not sent. Set VITE_WAITLIST_ENDPOINT in site/.env to post for real.`)
      await new Promise((resolve) => setTimeout(resolve, 400))
      return { ok: true, preview: true }
    }
    throw new Error(CONFIG_ERROR)
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 10000)

  let response
  try {
    // Form-encoded, not JSON. Loops' form endpoint parses a URL-encoded body and answers
    // "email is required" to a JSON one — the address is accepted by the browser, rejected by
    // the provider, and the visitor is told to try again for no reason they can see.
    response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
      body: new URLSearchParams({ [FIELD]: email }),
      signal: controller.signal,
    })
  } catch (err) {
    throw new Error(GENERIC_ERROR, { cause: err })
  } finally {
    clearTimeout(timeoutId)
  }

  // Loops answers 200 {"success": true}; a rejected address is 400 {"success": false, "message"},
  // and a flood is 429. An address already on the list is an ordinary success there, which is
  // also what it should look like to the person typing it — anything else leaks who is on it.
  if (response.ok) {
    const payload = await response.json().catch(() => null)
    if (payload === null || payload.success !== false) {
      return { ok: true }
    }
  }

  throw new Error(GENERIC_ERROR)
}
