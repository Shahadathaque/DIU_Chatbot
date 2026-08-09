import { describe, expect, it } from "vitest";
import { ApiError } from "../api";

describe("ApiError", () => {
  it("preserves status and message", () => {
    const error = new ApiError("Backend unavailable", 503);
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.message).toBe("Backend unavailable");
    expect(error.status).toBe(503);
  });
});
