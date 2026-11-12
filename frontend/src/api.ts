const BASE_URL = import.meta.env.VITE_API_URL || '';

export async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const response = await fetch(url, options);
  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API Request to ${endpoint} failed (${response.status}): ${errorBody}`);
  }
  return response.json();
}
