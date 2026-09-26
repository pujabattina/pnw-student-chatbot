import { render, screen } from "@testing-library/react";

import App from "./App";

describe("App", () => {
  it("renders the student chatbot heading", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "PNW Student Chatbot" }),
    ).toBeInTheDocument();
  });
});
