export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'include', ...options,
    headers: { ...(options.body && !(options.body instanceof FormData) ? {'Content-Type': 'application/json'} : {}), ...options.headers },
  })
  const data = await response.json().catch(() => ({detail: 'El servidor no está disponible. Inténtalo de nuevo.'}))
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('session-expired'))
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Revisa los campos e inténtalo de nuevo.')
  }
  return data as T
}
export const post = <T,>(path: string, data: unknown = {}) => api<T>(path, {method: 'POST', body: JSON.stringify(data)})

