# LinkedIn post draft: precarity by discipline

## Post text

Since May I've been scraping every job advert on jobs.ac.uk, once a day. About 7,000 so far. Leaving aside PhD studentships, which are training places rather than jobs, 58% of them are fixed-term.

That number is close to useless on its own, because it depends so much on the subject.

Biological sciences: 81% fixed-term. History and philosophy: 79%. Maths and physical sciences: 76%. Creative arts: 35%. Business and management: 33%.

Most of the gap comes down to what each discipline is actually hiring. Biology advertises six research posts for every lecturer post. Business advertises one research post for every six lecturer posts. Research posts are 95% fixed-term and lecturer posts 35%, so a research-heavy discipline ends up a fixed-term discipline almost by construction.

History and philosophy doesn't fit that. It advertises research and lecturer posts in roughly equal numbers and still sits at 79% fixed-term, above maths and physics. There's no grant-funding explanation for that one. It's teaching on temporary contracts.

Caveats, because there are real ones. It's one job board, which skews academic and research. It's one spring and summer, so I can't say anything about trends yet. And these are adverts, not people. Permanent posts turn over slowly, so the workforce is a lot more permanent than the vacancies make it look.

Chart attached. I have the per-discipline table if anyone wants it.

[Add one line in your own words: why you started scraping, or which number surprised you. That does more against AI suspicion than any editing.]

## Alternative opening (number first)

7,000 UK university job adverts since May, PhD studentships set aside. 58% fixed-term overall, but that runs from 33% in business to 81% in biological sciences, and the reason is mostly what each subject is hiring.

## Notes for you before posting

- PhD studentships (634 adverts, 96% fixed-term) are excluded from every fixed-term share, in the chart and in the text. Including them adds 3 to 4 points overall and 8 points to engineering, which is why they are out: they are not jobs and the objection is easy to anticipate.
- Numbers are as of 3 September 2026 and will drift slightly with each daily scrape. Re-run the chart script on the day you post if you want them exact.
- "Research posts" means titles containing research fellow, research associate, research assistant or postdoc. "Lecturer posts" means titles containing lecturer at any grade. Keyword classification, so treat the ratios as magnitudes.
- History and philosophy (ratio 1.03) is shown in grey as "balanced" (band 0.8 to 1.25) rather than forced into research-heavy or teaching-heavy. It is the only discipline in that band, which is what makes it the clean exception in the post. The band is `BALANCED_BAND` in `analysis/trends.py`, shared with the dashboard chart; re-run the PNG with `python -m scripts.casualisation_chart` on posting day (needs matplotlib).
- Languages, literature and culture is the other humanities outlier: 68% fixed-term on a teaching-heavy mix. Same story as history, if you want a second example.
- Professional and managerial adverts were excluded from the chart because they are a job type, not a discipline, in the source taxonomy.
- Expect the pushback "adverts are not jobs". The last caveat paragraph pre-empts it. The cleanest defence is that vacancy flow is what an applicant actually faces.
- The multi-discipline attribution fix from this week matters here: before it, social sciences and maths were undercounted three to four fold, which would have shifted their bars.
