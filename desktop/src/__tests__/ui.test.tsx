import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EncryptedNote } from "@/components/Credentials";
import { TagInput } from "@/components/TagInput";
import Unlock from "@/pages/Unlock";
import { split } from "@/pages/Onboarding";
import { formatBytes, titleCase } from "@/lib/utils";

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe("utils", () => {
  it("formats values", () => {
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(titleCase("awaiting_approval")).toBe("Awaiting Approval");
    expect(split("Python, Go\nRust,,")).toEqual(["Python", "Go", "Rust"]);
  });
});

describe("security copy", () => {
  it("states that keys stay local and encrypted", () => {
    render(<EncryptedNote />);
    expect(screen.getByText(/AES-256-GCM/)).toBeInTheDocument();
    expect(screen.getByText(/maintainers never receive it/)).toBeInTheDocument();
  });
});

describe("Unlock", () => {
  it("disables submit until a password is entered", () => {
    wrap(<Unlock />);
    const button = screen.getByRole("button", { name: "Unlock" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Master password"), { target: { value: "secret password" } });
    expect(button).not.toBeDisabled();
  });
});

describe("TagInput", () => {
  it("adds comma-separated tags without duplicates", () => {
    let value: string[] = ["Python"];
    const { rerender } = render(<TagInput label="Skills" value={value} onChange={(v) => (value = v)} />);
    const input = screen.getByLabelText("Skills");
    fireEvent.change(input, { target: { value: "python, Go" } });
    fireEvent.keyDown(input, { key: "Enter" });
    rerender(<TagInput label="Skills" value={value} onChange={(v) => (value = v)} />);
    expect(value).toEqual(["Python", "Go"]);
  });
});

describe("MatchRing", () => {
  it("fills the ring in proportion to the score and labels it", async () => {
    const { MatchRing } = await import("@/components/ui/misc");
    const { container } = render(<MatchRing score={75} />);
    expect(screen.getByRole("img", { name: "Match 75 out of 100" })).toHaveTextContent("75");
    const arc = container.querySelectorAll("circle")[1];
    const full = Number(arc.getAttribute("stroke-dasharray"));
    expect(Number(arc.getAttribute("stroke-dashoffset"))).toBeCloseTo(full * 0.25);
    expect(arc).toHaveClass("text-heat");
    const empty = render(<MatchRing score={0} />);
    expect(empty.container.querySelectorAll("circle").length).toBe(1); // track only, no arc
  });
});
