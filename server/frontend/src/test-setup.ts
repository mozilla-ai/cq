import "@testing-library/jest-dom/vitest";

// Node 25 provides a built-in localStorage that lacks the full Web Storage API
// when --localstorage-file is not configured. Override with a spec-compliant
// in-memory implementation for tests.
const storage = new Map<string, string>();

const localStorageMock: Storage = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => {
    storage.set(key, value);
  },
  removeItem: (key: string) => {
    storage.delete(key);
  },
  clear: () => {
    storage.clear();
  },
  get length() {
    return storage.size;
  },
  key: (index: number) => [...storage.keys()][index] ?? null,
};

Object.defineProperty(globalThis, "localStorage", { value: localStorageMock });
Object.defineProperty(window, "localStorage", { value: localStorageMock });
