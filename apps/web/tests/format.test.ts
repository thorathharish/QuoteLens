import { describe, expect, it } from "vitest";
import { stripCitations } from "@/components/copilot";
import { money, percent, quantity, sentence } from "@/lib/format";
import { SseParser } from "@/lib/sse";

describe("format", () => {
  it("formats API decimal strings without inventing values", () => {
    expect(money("4389.48", "USD")).toBe("$4,389.48");
    expect(money("0.7175", "USD")).toBe("$0.7175");
    expect(money(null)).toBe("—");
    expect(quantity("1000")).toBe("1,000");
    expect(percent("0.897", 1)).toBe("89.7%");
    expect(sentence("QUOTE_READY")).toBe("Quote ready");
  });
});

describe("SseParser", () => {
  it("parses events split across chunks", () => {
    const parser = new SseParser();
    expect(parser.push('event: token\ndata: {"text":"Hel')).toEqual([]);
    expect(parser.push('lo"}\n\nevent: done\ndata: {"grounded":true}\n\n')).toEqual([
      { event: "token", data: { text: "Hello" } },
      { event: "done", data: { grounded: true } },
    ]);
  });

  it("handles CRLF line endings and ignores empty blocks", () => {
    const parser = new SseParser();
    expect(parser.push('event: citations\r\ndata: {"items":[]}\r\n\r\n\n\n')).toEqual([
      { event: "citations", data: { items: [] } },
    ]);
  });
});

describe("copilot", () => {
  it("removes inline citation markers (sources are shown as chips)", () => {
    expect(stripCitations("Obsolete [E:ev_cmp_1] and short [E:ev_off_2].")).toBe("Obsolete and short.");
  });
});
