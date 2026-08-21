import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Footer } from "@/components/layout/footer";

describe("Footer", () => {
  it("keeps the author and official DIU links without the course link", () => {
    const markup = renderToStaticMarkup(createElement(Footer));

    expect(markup).toContain(
      'href="https://www.linkedin.com/in/shahadat-haque-fardin-77b084356/"',
    );
    expect(markup).toContain("Shahadat on LinkedIn");
    expect(markup).toContain('href="https://daffodilvarsity.edu.bd/"');
    expect(markup).not.toContain("elearn.daffodilvarsity.edu.bd");
    expect(markup).not.toContain("AI Lab course");
    expect(markup.match(/target="_blank"/g)?.length).toBe(2);
    expect(markup.match(/rel="noopener noreferrer"/g)?.length).toBe(2);
  });

  it("uses the admission-focused brand mark", () => {
    const markup = renderToStaticMarkup(createElement(Footer));

    expect(markup).toContain('d="M5.8 4.5h12.4');
    expect(markup).toContain('d="m7.3 10.2 4.7-2.5');
  });
});
