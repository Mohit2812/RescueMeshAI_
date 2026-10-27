
const API_URL =
  import.meta.env.VITE_API_URL ||
  "https://rescuemeshai-mdlk.onrender.com";

export async function checkBackend() {
  const response = await fetch(`${API_URL}/`);

  if (!response.ok) {
    throw new Error(`Backend error: ${response.status}`);
  }

  return response.json();
}
