import { notifyUnauthorized } from "./session";

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    let body: ApiErrorBody;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = {
        code: "unexpected_response",
        message: "服务暂时不可用，请稍后重试",
        details: {},
      };
    }
    return new ApiError(response.status, body);
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw await ApiError.fromResponse(response);
  }
  return response.status === 204
    ? (undefined as T)
    : ((await response.json()) as T);
}
