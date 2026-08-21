import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Footer } from "@/components/layout/footer";

describe("Footer", () => {
  it("links to the project author's LinkedIn profile and AI Lab course", () => {
    const markup = renderToStaticMarkup(createElement(Footer));

    expect(markup).toContain(
      'href="https://www.linkedin.com/in/shahadat-haque-fardin-77b084356/"',
    );
    expect(markup).toContain(
      'href="https://elearn.daffodilvarsity.edu.bd/course/view.php?id=36937"',
    );
    expect(markup).toContain("Shahadat on LinkedIn");
    expect(markup).toContain("AI Lab course");
    expect(markup.match(/target="_blank"/g)?.length).toBeGreaterThanOrEqual(3);
    expect(markup.match(/rel="noopener noreferrer"/g)?.length).toBeGreaterThanOrEqual(3);
  });
});
