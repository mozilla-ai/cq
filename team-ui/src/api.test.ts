import { describe, it, expect, beforeEach } from "vitest";
import { setToken, getToken } from "./api";

const STORAGE_KEY = "cq_auth_token";

describe("token persistence", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setToken(null);
  });

  it("persists token to localStorage on setToken", () => {
    setToken("test-jwt-token");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("test-jwt-token");
  });

  it("restores token from localStorage on getToken", () => {
    window.localStorage.setItem(STORAGE_KEY, "stored-token");
    expect(getToken()).toBe("stored-token");
  });

  it("clears localStorage when token is set to null", () => {
    window.localStorage.setItem(STORAGE_KEY, "stored-token");
    setToken(null);
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
