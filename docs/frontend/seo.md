# Frontend SEO and admission guides

The App Router owns canonical metadata, Open Graph/Twitter cards, JSON-LD,
`/sitemap.xml`, and `/robots.txt`. Set `NEXT_PUBLIC_SITE_URL` to the exact
production HTTPS origin before building. Optional Google and Bing verification
tokens are read from `GOOGLE_SITE_VERIFICATION` and
`BING_SITE_VERIFICATION`.

The typed guide catalog is in `frontend/content/guides.ts`. Every guide must be
substantial, cite only registered official DIU sources, show its updated date,
and avoid unsupported or date-sensitive claims. Add a guide to that catalog;
the route, metadata, JSON-LD, related links, and sitemap entry are generated
from the same record.

Individual program pages are intentionally deferred. The current programs UI
loads a small runtime catalog and does not have enough server-rendered,
program-specific evidence to justify dozens of useful indexable pages. Creating
them now would produce thin pages. Revisit only when verified structured
program, tuition, provenance, and updated-date fields can be rendered on the
server.

After production deployment, submit `/sitemap.xml` in Google Search Console and
Bing Webmaster Tools. Verification and submission require the site owner's
provider accounts and are therefore manual operational steps.
