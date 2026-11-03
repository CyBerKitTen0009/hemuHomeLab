let csrf = '';
export function setCsrf(value: string) { csrf = value; }
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
  const response = await fetch('/api' + path, {
    method, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(method !== 'GET' ? {'X-CSRF-Token': csrf} : {}) },
    ...(data !== undefined ? { body: JSON.stringify(data) } : {})
  });
  const result = await response.json();
  if (!response.ok) {
    let message = result.detail;
    if (Array.isArray(message)) message = message.map((item: {msg: string}) => item.msg).join('；');
    if (typeof message === 'object') message = message.message;
    throw new ApiError(response.status, message || '请求失败，请稍后重试');
  }
  return result;
}
