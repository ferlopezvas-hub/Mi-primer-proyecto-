import { render, screen } from "@testing-library/react";
import { ProbabilityBar } from "./ProbabilityBar";

test("muestra cada resultado con texto (no solo color) y en orden local-empate-visitante", () => {
  render(<ProbabilityBar market="1x2" probabilities={{ away: 0.2, home: 0.5, draw: 0.3 }} pick="home" />);
  const img = screen.getByRole("img");
  expect(img.getAttribute("aria-label")).toBe("Local 50 %, Empate 30 %, Visitante 20 %");
  expect(screen.getByText("50 %")).toBeInTheDocument();
});
