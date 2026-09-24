# LinkedIn post draft: what a UK academic job advert tells you depends on the career stage

Companion chart: `python -m scripts.career_stage_chart` (writes `reports/he_career_stage.png`).
Run it against the live database (see notes).

## Post text

Since May I've collected every job advert on jobs.ac.uk, once a day. Leave out PhD studentships and posts outside the UK and that's about 6,500 UK university jobs. Sort them by career stage and three things move in opposite directions.

Security goes up with seniority. 94% of research and postdoc adverts are fixed-term. Lecturers, 37%. Senior lecturers, 13%. Associate professors and professors, about 10%.

Pay transparency goes down. 98% of postdoc adverts state a salary. Almost half of professor adverts (45%) give no figure at all: "competitive", "negotiable", or nothing.

Time to apply goes up. A third of postdoc and teaching-fellow adverts close within 14 days of being posted. For professors it's about one in nine, and the typical advert stays open a month rather than three weeks.

Put together: the people with the least bargaining power are told exactly what the job pays, given the least time to apply, and offered a contract that ends. The people with the most are invited to negotiate and given the time to do it.

Teaching fellows and tutors deserve their own line. 60% of those adverts are fixed-term and 45% are part-time. That is where temporary teaching sits.

Caveats. These are adverts, not the people in post, from one job board over one spring and summer. Career stage comes from the job title, so some titles land in the wrong group. The professor figures rest on 88 adverts. Research posts are fixed-term largely because grants are; the chart shows that, it doesn't excuse it.

[Add one line in your own words: what you'd tell a postdoc who's reading this, or what you expected before seeing it.]

## Alternative opening (chart first)

Three bars per career stage, from 6,500 UK university job adverts. Postdocs: 94% fixed-term, 2% with no pay figure. Professors: 10% fixed-term, 45% with no pay figure. The further up the ladder, the less the advert tells you and the longer you get to apply.

## Notes for you before posting

- Numbers as of 24 September 2026, from the live database. Re-run on posting day against a fresh snapshot of the server's database (the local `data/jobs.db` is stale, and the server venv has no matplotlib):
  `ssh he-market "sqlite3 -readonly /opt/he-market-analysis/data/jobs.db '.backup /tmp/jobs_snapshot.db'"`
  `scp he-market:/tmp/jobs_snapshot.db live.db`
  `python -m scripts.career_stage_chart --db live.db --table`
- "No pay figure" counts adverts with no salary and no hourly rate. Hourly-paid adverts are counted as stating pay. Without that correction teaching fellows would read 16% rather than 3%.
- Professors: 45% give no figure. Associate professors and readers: 10%. Directors, heads and deans (not in the chart, a mix of academic and professional services): 25%.
- Median days to apply: 21 for postdocs, 19 for teaching fellows, 20 for lecturers, 28 for associate professors, 30 for professors.
- Part-time share: teaching fellows 45%, lecturers 31%, senior lecturers 20%, postdocs 11%, professors 10%.
- "Least bargaining power" is your interpretation, not a measured fact. Keep it if you're comfortable owning it.

## Other angles, if you want a second post

Each is checked against the live data (24 September 2026) but has no chart yet.

- **Two universities post a quarter of UK research jobs.** Oxford and Cambridge placed 24% of UK research and postdoc adverts (602 of 2,555), and 14% of all UK adverts, out of 358 UK employers. UCL, Edinburgh and Queen Mary follow at about 100 each. It's a strong line, but it's about where the grant money is, not about precarity.
- **The London premium is bigger than London weighting.** The median advertised salary floor for full-time lecturers in London is £51,753, against £42,254 in the rest of England. For postdocs it's £45,031 against £37,694. London weighting explains only part of that gap. The rest is probably which institutions recruit in London (Imperial, UCL, King's pay higher scales), so treat it as a mix effect unless you control for employer.
- **Weekend deadlines.** Sunday is the most common closing day (23% of UK adverts), then Monday (20%). Almost nothing is posted at the weekend. That's a light, relatable post.
- **One advert in ten is overseas.** 10% of adverts on the UK board are for posts outside the UK, and 30% of those are in Ireland (Dublin, Galway, Limerick, Cork, Maynooth).
