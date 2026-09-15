/**
 * The only network call the marketing page makes.
 *
 * Phase 1 posts to a hosted form provider named by VITE_WAITLIST_ENDPOINT. Phase 2 (a
 * Supabase-backed table behind POST /api/waitlist) replaces the body of submitWaitlist and
 * touches nothing else — see docs/landing-page-spec.md section 8.
 *
 * The messages a visitor sees live in content/shared.jsx with the rest of the copy; only the
 * behaviour is here.
 */

import { WAITLIST } from '../content/shared'

const { unconfigured: CONFIG_ERROR, network: GENERIC_ERROR } = WAITLIST.errors

// A provider that already holds this address answers 409 (or 422). That is a success for the
// person signing up, and telling them otherwise both confuses them and leaks whether an
// address is on the list.
const ALREADY_SUBSCRIBED = new Set([409, 422])

// Providers disagree on what to call the field: Loops and Formspark take `email`, Buttondown's
// API takes `email_address`. One env var beats editing this file when the provider is chosen.
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
    response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ [FIELD]: email }),
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
