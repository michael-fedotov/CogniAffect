export const API_BASE =
  typeof window !== 'undefined' &&
  window.location.hostname === 'michael-fedotov.github.io'
    ? 'https://cogniaffect.onrender.com'
    : '';

export function apiUrl(path) {
  return path.startsWith('http') ? path : `${API_BASE}${path}`;
}
