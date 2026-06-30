export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

async function readResponseBody(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

function parseErrorMessage(status: number, body: unknown): { message: string; detail: unknown } {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') {
      return { message: detail, detail }
    }
    if (detail && typeof detail === 'object') {
      const d = detail as { message?: string }
      return { message: d.message ?? `Request failed (${status})`, detail }
    }
  }
  return { message: `Request failed (${status})`, detail: body }
}

export async function request<T>(
  path: string,
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = 30000, ...init } = options
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...init.headers,
      },
    })

    if (!res.ok) {
      const body = await readResponseBody(res)
      const { message, detail } = parseErrorMessage(res.status, body)
      throw new ApiError(res.status, message, detail)
    }

    if (res.status === 204) {
      return undefined as T
    }

    const body = await readResponseBody(res)
    return body as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError(408, 'Request timed out')
    }
    throw new ApiError(0, err instanceof Error ? err.message : 'Network error')
  } finally {
    clearTimeout(timeout)
  }
}

/** Multipart upload — do not set Content-Type (browser sets boundary). */
export async function requestFormData<T>(
  path: string,
  formData: FormData,
  options: { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = 180000, ...rest } = options
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
      ...rest,
    })

    if (!res.ok) {
      const body = await readResponseBody(res)
      const { message, detail } = parseErrorMessage(res.status, body)
      throw new ApiError(res.status, message, detail)
    }

    const body = await readResponseBody(res)
    return body as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError(408, 'Request timed out')
    }
    throw new ApiError(0, err instanceof Error ? err.message : 'Network error')
  } finally {
    clearTimeout(timeout)
  }
}
