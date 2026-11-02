import { outcomeLabel, pct, statusText } from "./format";
import type { Match } from "./types";

const m = { sport: "football", status: "live", status_detail: "HT", elapsed: 45, start_time: "2026-11-08T20:00:00Z",
  home: { name: "A" }, away: { name: "B" } } as unknown as Match;

test("pct", () => {
  expect(pct(0.5288, 1)).toBe("52.9 %");
  expect(pct(null)).toBe("—");
});
test("estado del partido", () => {
  expect(statusText(m)).toBe("Descanso");
  expect(statusText({ ...m, status_detail: "2H", elapsed: 67 })).toBe("67'");
});
test("etiquetas de resultado", () => {
  expect(outcomeLabel("1x2", "home", m)).toBe("A");
  expect(outcomeLabel("btts", "yes")).toBe("Sí");
});
