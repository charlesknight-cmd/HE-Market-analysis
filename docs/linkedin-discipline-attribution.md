# LinkedIn post draft: why subject counts from job boards are wrong

Companion chart: `python -m scripts.attribution_chart` (writes `reports/he_discipline_attribution.png`).

## Post text

Every "most in-demand subjects" chart built from a job board has a quiet assumption in it: that a job belongs to one subject. On jobs.ac.uk it doesn't. Of the 7,000 adverts I've collected since May, 44% are tagged with two or more disciplines. One fellowship call is tagged with twenty.

My first version of this stored one discipline per advert: whichever facet my scraper happened to check first. Alphabetical, as it turned out. Agriculture and biological sciences came out fine. Social sciences came out at a fifth of its real size. Information management at less than a third. I only noticed because the numbers looked odd against the site's own counts.

So I fixed it and tried the obvious better rule: take the first subject listed on the advert's page. That's what I'd have done from the start if I'd been paying attention. It's still wrong, just less obviously. The site lists an advert's subjects in a fixed order, so health and medical is almost never undercounted, and engineering loses two out of every three adverts. Chart attached. Same 7,000 adverts, counted once versus counted under every subject they carry.

The point isn't my bug. It's that there is no neutral single-label rule. Whatever rule you pick is a hidden ordering, and the ordering decides which subjects look big. The only count that doesn't smuggle in a ranking is to let each advert count under every subject it carries, and to say so. That means subject counts add up to more than the number of adverts, which bothers people. It's still the right number.

If you're reading a subject-demand chart from a job board, ask how they handled multi-subject adverts. If the answer is "we didn't", the ranking is partly the taxonomy's order.

Caveats. One board, one spring and summer, academic and research heavy. And some of the multi-tagging is generic: a "research fellowships" round tagged with every science inflates all of them a little. Capping tags per advert would change the small subjects most.

[Add one line in your own words on how you spotted it, or what you'd have said about social sciences before the fix.]

## Alternative opening (chart first)

Same 7,000 job adverts, counted two ways. Light dot: each advert counted once, under its first-listed subject. Dark dot: counted under every subject it carries. Engineering triples. Health barely moves. The gap is the site's taxonomy order, not the job market.

## Notes for you before posting

- Numbers as of 3 September 2026. Re-run the chart script on posting day; the subject tags update with each daily scrape.
- "First-listed" is the `jobs_primary_discipline` view; "every subject" is `jobs_by_discipline`. The alphabetical version is the raw `jobs.category` column. All three are in the script's `--table` output if you want to quote them.
- Ratios under the first-listed rule range from 1.0 (agriculture, health) to 4.3 (information management). Engineering is 3.0, politics 2.9, social sciences 2.4, maths 2.3. Under the old alphabetical rule social sciences was 5.0 and media 4.8.
- The most common pairings are engineering with physical sciences (495 adverts), biology with health (458), and computer science with maths (357). Useful if someone asks "which subjects overlap".
- 219 adverts have no academic subject at all (professional services, tagged only with non-academic areas). They fall back to the facet they were found in, which is stated in the chart footer.
- Expect "just cap it at one subject and pick the primary". The reply is the chart: the primary is whatever the taxonomy lists first, and that is not a property of the job.
- Expect "then the shares don't sum to 100". Correct. Shares of tags, not of adverts. Say it once and move on.
