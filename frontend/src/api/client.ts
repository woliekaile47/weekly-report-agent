export const API_BASE_URL = "/api";
export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API_BASE_URL + url, init);
  if (!response.ok) {
    const value = await response
      .json()
      .catch(() => ({ detail: "服务请求失败" }));
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : JSON.stringify(value.detail),
    );
  }
  return response.json() as Promise<T>;
}
export const streamUrl = (id: string) => `${API_BASE_URL}/runs/${id}/stream`;
export const fileUrl = (id: string, kind: string) =>
  `${API_BASE_URL}/runs/${id}/download/${kind}`;
