import { afterEach, describe, expect, it, vi } from "vitest";

import { copyText } from "./clipboard";

const originalExecCommand = document.execCommand;

afterEach(() => {
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: originalExecCommand,
  });
});

describe("copyText", () => {
  it("uses the asynchronous Clipboard API when it succeeds", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    await expect(copyText("规范结果")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("规范结果");
  });

  it("falls back to a temporary textarea when Clipboard API rejects", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("blocked")) },
    });
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand,
    });

    await expect(copyText("7亿8593万4455")).resolves.toBe(true);
    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(document.querySelector("[data-copy-fallback]")).toBeNull();
  });

  it("returns false when both copy mechanisms fail", async () => {
    vi.stubGlobal("navigator", {});
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn().mockReturnValue(false),
    });

    await expect(copyText("无法复制")).resolves.toBe(false);
  });
});
