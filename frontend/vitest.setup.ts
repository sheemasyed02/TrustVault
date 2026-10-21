import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";

afterEach(() => {
  cleanup();
});