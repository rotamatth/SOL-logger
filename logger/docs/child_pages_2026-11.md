# Child pages against the Figma, November 2026

Matthias tried the first deployed version on an iPad on 6 November with the test IDs and compared it with
Diletta's Figma. This page records what was wrong on each page, why, and what changed, so the choices are
not lost. The pictures are in [`child_pages_2026-11/`](child_pages_2026-11/) and show test IDs and test answers only.

"Before" pictures come from that iPad, cropped to the page. The old recap comes from a rehearsal of the same version on a computer,
because the iPad picture of it was not saved. "After" pictures come from the real app, at 1280 x 680, the size of a shorter tablet in
a browser. They are not from a classroom tablet: see fix 8.

## What was decided, and by whom

| Topic | Matthias's decision |
| --- | --- |
| First answer page | Keep the confirmation step of issue #6 (Conferma, then the search button on the same page), although the Figma has none |
| Button to the search | Keep the wording "Entra nel motore di ricerca", not the Figma's "Ora cerca con Google" |
| Review page | The Figma's layout, without the question text |
| Final recap | Until 8 November: the three session columns with the Figma's graphics. From 8 November: Diletta's one picture of today's questions, numbered in the order the child met them, with no editing (fix 23) |
| The child's stars on the recap | Kept, although the Figma has none |
| The recap's PDF | Kept on the server only; researchers download it from the dashboard (fixes 24 and 31) |
| Answer cards | The subtitle's size, on the page after each question and on the recap (fix 25) |
| "Cominciamo!" and the question introduction | Add both, with a text for each theme in the style of Diletta's spazio text |
| "Indietro" on question pages | Not added: the flow goes one way |
| Fonts | The Figma's Poppins and Nunito |
| Logo | Stays "Cerca con SOL" for now; Diletta may ask for "Cerca con LUNA" |
| May's experiment | Listed under past sessions as "Esperimento 19 maggio" |

## The fixes

### 1. The search button before there is an answer

![Before](child_pages_2026-11/before-form.jpg) ![After](child_pages_2026-11/after-form.jpg)

**Was:** a pale "Entra nel motore di ricerca" was on screen from the start, and a child would try to tap it.
**Cause:** the button was drawn disabled, as in the Figma.
**Now:** the button does not exist until the answer is confirmed. Issue #6 already asked to "reveal" it.

### 2. Conferma and "Non lo so" of different sizes

![After, typed](child_pages_2026-11/after-typed.jpg)

**Was:** "Conferma risposta" was longer than "Non lo so", and placed elsewhere on the page.
**Now:** "Non lo so" and "Conferma" are two equal buttons beside the answer box. Each fades when it cannot be used
yet, but stays tappable, so a child who taps "Conferma" early is told what is missing.

### 3. The "Non lo so" pop-up

![Before](child_pages_2026-11/before-dialog.jpg) ![After](child_pages_2026-11/after-dialog.jpg)

**Was:** two buttons of different widths, stacked, with a thick ring around the first.
**Cause:** the ring is the keyboard focus mark, drawn because the pop-up focuses its first button when it opens.
**Now:** two equal buttons side by side. The ring is gone on touch screens and stays for keyboards.

### 4. How the first answer is shown

![Before: Non lo so](child_pages_2026-11/before-saved-unknown.jpg) ![Before: written](child_pages_2026-11/before-saved.jpg)
![After](child_pages_2026-11/after-saved.jpg) ![Before: pop-up](child_pages_2026-11/before-popup.jpg)
![After: pop-up](child_pages_2026-11/after-popup.jpg)

**Was:** "Non lo so" looked like a button, a written answer looked like a box to write in, and the
"La mia prima risposta" pop-up had a layout of its own.
**Now:** the pop-up has the layout of the `?` pop-up: coloured strip, light bulb, label and the answer in large text.
The confirmed page uses the same label and text. Neither looks like something to tap or type in.

### 5. The black background of the animations

![Before](child_pages_2026-11/before-review.jpg) ![After](child_pages_2026-11/after-review.jpg)

**Was:** a black rectangle around each animation on the iPad.
**Cause:** the supplied MP4s have a black background. A browser filter hid it, and that filter works on a computer but did not
on the iPad. Every automated test passed, because they run on a computer.
**Now:** the six clips are re-encoded on the white of the page, so no browser has to hide anything.
`tools/prepare_review_media.py` makes them from the supplied files, and can be run again if originals with
a transparent background arrive.

### 6. The size and proportion of the animations

**Was:** each picture filled only 21-47% of the width of a 4K frame, off-centre, shown at most 240 px high. The
page was taller than the screen, so "Prossima domanda" was below the fold.
**Cause:** each clip is a piece of the big recap picture, in its place in that picture.
**Now:** each clip is cropped to its picture and fills a stage of about 400 px, with the answer cards on it as in the Figma's
"Pieces Unlock", the line "Avete sbloccato il primo riassunto delle vostre risposte!" and the button.

![After, inside of the ear](child_pages_2026-11/after-review2.jpg) ![After, animals](child_pages_2026-11/after-review3.jpg) ![After, spazio](child_pages_2026-11/after-review-spazio.jpg)

### 7. Two orecchio clips were swapped

**Was:** `Orecchio_02.mp4` showed the animals and `Orecchio_03.mp4` the inside of the ear, while their stills, the recap
picture and the Figma go child, inside of the ear, animals.
**Now:** the files are swapped to match. **In the question editor: box 1 is the child with a hand to the ear, box 2 the inside
of the ear, box 3 the animals.** The stills are now the last frame of each clip, so the two can no longer disagree.

### 8. Screens shorter than an iPad

**Was:** on the iPad the question pages needed scrolling, and the classroom tablets are shorter still. The blue band at the top was
84 px, kept for an "Indietro" button these pages do not have.
**Now:** the band is 34 px, sizes follow the screen height, and heights follow the part of the screen the browser really shows. The steps of a question
fit at 1180 x 699, 1280 x 680 and 1024 x 520 without scrolling to the button, and a browser test keeps it so.
**Still needed:** a check on a real classroom tablet. They are not iPads, and their browser has not been tried.

### 9. Final recap

![Before](child_pages_2026-11/before-recap.jpg) ![After](child_pages_2026-11/after-recap.jpg)
![After saving](child_pages_2026-11/after-recap-saved.jpg) ![After, spazio](child_pages_2026-11/after-recap-spazio.jpg)

**Was:** wide columns and a large "Non ci sono risposte" box hid the picture, and the Figma's colours and buttons were missing.
**Now:** the picture stays in view, with narrow columns on top, orange labels, translucent cards as in the Figma and stars for the self-assessment.
"Salva l'attività" is orange. After saving, the buttons are "Scarica PDF" and "Chiudi".
**Unchanged:** three session columns, the arrows, editing and viewing the original, the PDF, what is saved and what is logged.
Session 3 used to say "termina lo studio" on its button. It now says "Salva l'attività" too, and still ends the study.

### 10. New pages: "Cominciamo!" and the question introduction

![Cominciamo](child_pages_2026-11/after-cominciamo.jpg) ![Introduction](child_pages_2026-11/after-intro.jpg)

"Cominciamo!" opens a run, with a text for its theme. The introduction opens each question.
The spazio text is Diletta's. **The orecchio text is written in the same style and Diletta should check it:**

> In classe state studiando le curiosità del corpo umano.
> Avete da poco incontrato l'orecchio, con le sue parti e i suoni che ci fa sentire.
> Ma ci sono ancora tante cose da imparare!

The introductions log nothing. `TaskStarted` stays where issue #6 puts it, when the answer form first appears. A question already begun
resumes at its form, without the introduction.

### 11. May's experiment in Sessions

![After](child_pages_2026-11/after-sessions.jpg)

**Was:** the year 2025/2026 said "No sessions yet", although May's records are in Data and history.
**Now:** Past sessions lists "Esperimento 19 maggio" ("19 May experiment" in English) per class, with its number of IDs and a link to its data. These rows are read from
the historical rules and are not sessions: a real May session would make Tuesday's class 4 "Session 2" and end the study one session early.

### 12. A test ID's first event in the real log folder

**Was:** a tester who left a test run at its introduction kept the choice of ID unsent in the browser. It went out during the next child's run on that tablet, and with no run on the server to look up it landed in the real folder. The dashboard ignored the file, so no result changed.
**Now:** a batch with no run on the server goes to the test folder when every event in it belongs to a test ID. Found by the shared-tablet rehearsal.

### 13. Back on an introduction

**Was:** the browser's Back from "Cominciamo!" reached the start page, which opened the answer form and logged `TaskStarted`, skipping the introductions.
**Now:** Back returns to the introduction. The question starts only when the child taps "Inizia".

### 14. "Avvia animazione"

**Was:** on a tablet that blocks autoplay, the button sat on top of an answer card. It also appeared for a clip that could not load, where it did nothing.
**Now:** it sits beside "Prossima domanda", and only when a tap can help. A clip that cannot load leaves its still on screen.

## Second iPad test, 7 November

Matthias ran a test ID through the deployed pages on the iPad. "Before" pictures come from that iPad, cropped to the page. "After" pictures
come from the real app at 1280 x 680 with a test ID. Two differ: the Italian warning is drawn by the browser and comes from Chromium, and the pictures of fix 18 are at 1180 x 699 with a real ID, whose closing page shows no number.

### 15. Warnings in English

![Before](child_pages_2026-11/before-warning-english.jpg) ![After](child_pages_2026-11/after-warning-italian.jpg)

**Was:** tapping "Conferma" without stars showed "Select one of these options".
**Cause:** for a required field the browser writes its own warning, in the tablet's language. The earlier tests ran on a computer and read only whether the form was refused.
**Now:** the forms turn the browser's warning off. The page asks for the same thing in the same place, in Italian: "Scegli quanto è giusta la tua risposta." and
"Scrivi una risposta oppure scegli “Non lo so”.". The number on the start page uses its existing "Seleziona un numero".
The error pages a child could reach, the start page's message and the tab title were in English too, and are now in Italian. `searchError` still logs `Connection Error`, so log analysis keeps its value.

### 16. The question above the confirmed answer

![Before](child_pages_2026-11/before-saved-prompt.jpg) ![After](child_pages_2026-11/after-saved-no-prompt.jpg)

**Was:** the page with the confirmed answer still asked "Pensi di sapere la risposta a questa domanda?".
**Now:** that line appears only while the form is open.

### 17. "Load failed" while editing the recap

![Before](child_pages_2026-11/before-recap-load-failed.jpg) ![After](child_pages_2026-11/after-recap-saved-draft.jpg)

**Was:** editing "Cosa sai adesso" showed "Load failed" under the answer. That is the browser's own wording for a request that never got a reply, and the page printed it as it was.
**Likely cause:** the server closed an idle connection after 2 to 3 seconds, Gunicorn's default. A tablet that sends a save just as that happens gets an immediate failure. The server keeps no access log, so what happened on the iPad at 12:58 cannot be confirmed. A dropped VPN would look the same, and the fix covers it too.
**Reproduced** in WebKit on the production image, with 40 ms added each way as a VPN does, typing one letter every 2 to 3 seconds:

| Version | Saves | Failed requests | Shown to the child |
| --- | --- | --- | --- |
| Before | 150 | at least 9 | 9, "Load failed" |
| Repeats only, server still at 2 seconds | 150 | 7 | 0 |
| Repeats and the server at 75 seconds, as released | 150 | 0 | 0 |

**Now:** the server holds an idle connection for 75 seconds. WebKit closed idle connections itself after about 29 seconds when measured, so the browser closes first. A failed save is repeated up to three times within about 4 seconds, on the recap and on the drafts of the first and final answers. The server accepts a repeat of the same recap save.
If the connection stays down, the child reads "Connessione non disponibile. Il testo resta qui: riprova." and the text stays. "Salva modifiche" tries again.

![With no connection](child_pages_2026-11/after-recap-no-connection.jpg)

### 18. The recap stuck after a long pause

![Before](child_pages_2026-11/before-recap-blocked.jpg) ![After, at the start page](child_pages_2026-11/after-limit-start.jpg) ![After, once the number is picked](child_pages_2026-11/after-limit-back.jpg)

**Was:** after more than 60 minutes on the recap, every save and "Salva l'attività" answered "Salvataggio non disponibile. Riprova.", for ever. The iPad pictures of fixes 17 and 18 are 64 minutes apart.
**Cause:** the 60-minute limit ends the session. Past it the recap's routes answer 404, and the page treated that as a failure to retry. Reproduced on the production image with the clock moved on: the same message, from the same 404.
**Now:** the page reopens, once, and the server sends the child to the start page as on every other page. Picking the number shows "Hai risposto alle tre domande" and "Chiudi l'attività".
Tried with real IDs for typing, "Salva modifiche", "Salva l'attività" and "Chiudi". A test ID past the limit starts a new run instead, because test runs repeat freely.
**Unchanged:** the 60 minutes, and the rule that a returning browser never shows the recap again, which keeps one child's answers from the next child on that tablet.
**What this means:** the answers of each question were already saved. A recap change made past the limit is not kept, and that run gets no PDF and no `studySessionFinished` unless "Salva l'attività" came first. See "Noticed and left for Matthias".

### Rehearsal on these fixes

On the production image with stand-in search, not on a real tablet: Tuesday with 20 children and test IDs, one tablet shared by both classes, every server process killed during a class (back in 2.1 s), 9 faults and researcher changes during class, all with no log damage.

**One of the six Tuesday runs went differently:** 18 of 20 finished, still with no log damage. ID 19 got "Salvataggio non disponibile" at the start page, and ID 1 saved its activity but the robot's "Chiudi" did not move on. The reason was not recorded, because that run kept only a summary. It did not recur in the other five.
Four of those were a direct comparison, two runs with the server's connection setting at 75 seconds and two at 2 seconds. All four finished 20 of 20, so the setting shows no sign of causing it. A burst of 20 children tapping "Continua" in the same instant, twice, answered everyone within 0.33 s. The start page now writes the reason to the server's log if it ever fails again. It says "riprova", and a new try works.

## Independent review, 7 November

Codex checked fixes 15-18 on `cece042`, without changing the code. Its report is `codex_investigation_2026-11-07_findings.md`, if Matthias keeps it in the repository; its evidence is on Matthias's Mac. Its run ended before the final write-up, so the report still says "verification is still running". It answered all seven questions. It found no damage to saved logs or answers. Fixes 19-22 come from it.

### 19. Recap buttons that did nothing when tapped early

![After, while the page opens](child_pages_2026-11/after-recap-buttons-waiting.jpg)

The picture was taken with the script blocked, because the state lasts only a moment.

**Was:** "Salva modifiche", "Salva l'attività" and "Chiudi" looked ready before their script had started, so an early tap was lost. In rehearsals 4 to 9 of 20 children needed a second "Chiudi" tap.
**Now:** the buttons look faded and cannot be tapped until they work. The second tap fell to 0 of 20 in both Tuesday runs, measured by the corrected robot.

### 20. A false "La bozza è cambiata"

**Was:** if the reply to a first or final answer draft was lost, the repeat was refused as an old revision. The child read that the draft had changed, and further draft saves stopped. "Conferma" still worked. The automatic repeat of fix 17 made this easier to reach.
**Now:** the server accepts the exact same save again. Other text, other stars and older revisions are still refused.

### 21. The last English labels

The tab on the results page said "Cerca - Search Results". It now says "Cerca - Risultati". The pagination label, the thumbnail's text and the viewer's title are in Italian too.

### 22. Stopping the server

**Was:** at `--keep-alive 75`, a browser connection open during a stop led to a hard kill (exit 137) after about 3.3 seconds. Without such a connection the server stopped cleanly. No data was at risk in the crash rehearsals, but a clean stop is better before the deploy's backup.
**Now:** `--graceful-timeout 2`: the server exits by itself (exit 0) in 2.4 seconds, measured on the production image with one idle connection.

### What the review changed in the findings above

- **ID 19's error.** The start page gives up after 2 seconds waiting for its lock (`TimeoutError: Admission busy`). Codex reproduced this for 2 of 20 children under much heavier load, with the server, 24 browsers, exports and PDFs on one Mac, and a retry worked. This is the leading explanation for ID 19, not a proven one. The 2 seconds stay as they are: the disk here is fast, and 20 starts with nothing else running answered within 0.33 s.
- **Fix 17's connection setting.** Full-page forms failed 1 to 2% of the time at the old 2 seconds and 0 of 400 at 75 seconds, in a small test app. The cause on the iPad is still not proven.
- **The rehearsal robot.** It could count a child as finished when the recap failed, and could report a second tap when a page was only slow to load. Both are corrected for the Tuesday runs from fix 19 on. Earlier "finished" counts are weaker than they looked, although the last comparison run was checked by hand: all 20 had their finishing event.

## Diletta's feedback, 8 November

Diletta tried the app on a tablet on 8 November and sent her points by priority, with the Figma frames of the final recap for spazio and orecchio. Matthias answered each point; fixes 23-32 follow from that. The orecchio sites that do not display are Samuele's, who received the same message, and are not part of this change.

"Before" pictures come from the version of 7 November (`a9b3f68`), "after" pictures from this one, both on the production image at 1280 x 680 with test IDs and made-up answers. The dashboard pictures come from a dashboard with synthetic runs.

### 23. The final recap: one picture of today's questions

**Was:** three session columns, the arrows between questions, editing ("Tocca per modificare", "Salva modifiche", "Vedi l'originale") and "Scarica PDF". Diletta: the children cannot change anything in this session, so talking about changing answers in later sessions is a concept they cannot try yet.
**Now:** the whole drawing of today's activity, as in her Figma. Over each question's part of it, an orange "Domanda 1", "2" or "3" gives the order in which the child met that question, as Diletta asked ("domanda 1,2,3 a seconda dell'ordine che è apparso loro"). Under it, "Cosa sapevi prima", the dashed arrow and magnifier, and "Cosa sai adesso", as on the page after each question. The stars of the child's own rating sit on the top edge of the first card: Matthias kept them. The only button is "Salva l'attività". After it the page says "La sessione è salvata.", the drawing stays, and "Chiudi" is the only button.
**Where the cards sit:** a question's part of the picture is its slot, the one that also picks its clip, at the positions of Diletta's two frames, moved inside the picture (fix 34). If the theme has no picture, or the three questions do not fill the three slots, they stand side by side instead.
**Unchanged:** what "Salva l'attività" saves and logs, including the PDF the server makes at that moment. The server still accepts drafts of earlier sessions; no page sends them now.

| Before | After |
| --- | --- |
| ![Before, orecchio](child_pages_2026-11/before-r3-recap-orecchio.jpg) | ![After, orecchio](child_pages_2026-11/after-r3-recap-orecchio.jpg) |
| ![Before, spazio](child_pages_2026-11/before-r3-recap-spazio.jpg) | ![After, spazio](child_pages_2026-11/after-r3-recap-spazio.jpg) |

| Before, saved | After, saved | After, long answers at 1024 x 520 |
| --- | --- | --- |
| ![Before](child_pages_2026-11/before-r3-recap-saved.jpg) | ![After](child_pages_2026-11/after-r3-recap-saved.jpg) | ![Long answers](child_pages_2026-11/after-r3-recap-long.jpg) |

A long answer scrolls inside its card, cut at a whole line, and no card reaches another. A browser test checks this at 1180 x 699, 1280 x 680 and 1024 x 520, before and after saving.

### 24. No PDF on the tablet

**Was:** "Scarica PDF" saved a file on the tablet, which both classes share.
**Now:** nothing is saved on the tablet, as Diletta asked. The server still keeps the PDF, and researchers download it from the dashboard (fix 31).

### 25. The answer cards at the subtitle's size

**Was:** the two cards on the page after each question had smaller text than the line under the title, hard to read on a tablet.
**Now:** the cards are a little bigger, with the subtitle's size, on that page and on the final recap.

| Before | After |
| --- | --- |
| ![Before](child_pages_2026-11/before-r3-review.jpg) | ![After](child_pages_2026-11/after-r3-review.jpg) |

### 26. Small grey hints and the repeated question

**Was:** "Pensi di sapere la risposta a questa domanda?" above the question, which the introduction had just asked; "Conferma la tua risposta per iniziare la ricerca." under the answer box; "Prima risposta confermata. Ora puoi cercare informazioni." after confirming.
**Now:** all three are gone. A message about a failed save still appears, only when it happens.

| Before | After |
| --- | --- |
| ![Before](child_pages_2026-11/before-r3-form.jpg) | ![After](child_pages_2026-11/after-r3-form.jpg) |

### 27. "La tua prima risposta è:"

**Was:** "La tua prima risposta è la seguente:".
**Now:** "La tua prima risposta è:", on the answer page and in the "La mia prima risposta" pop-up. The "?" pop-up keeps "La domanda a cui devi rispondere è la seguente:".

| Before | After |
| --- | --- |
| ![Before](child_pages_2026-11/before-r3-saved.jpg) | ![After](child_pages_2026-11/after-r3-saved.jpg) |

### 28. The same round ✕ on both pop-ups

**Was:** the ✕ of "La mia prima risposta" had no circle. The circle Diletta saw on the "?" pop-up was the browser's focus ring, there only while the button had focus.
**Now:** both buttons draw the same light-blue ring themselves. See also fix 33.

| Before | After | The "?" pop-up, after |
| --- | --- | --- |
| ![Before](child_pages_2026-11/before-r3-popup.jpg) | ![After](child_pages_2026-11/after-r3-popup.jpg) | ![After](child_pages_2026-11/after-r3-popup-help.jpg) |

### 29. May's questions named in the dashboard

**Was:** May's logs record only the topic number, so a child's page read "1. 3".
**Now:** "1. Altre galassie", from `data/user_topics.csv`, the file May's app read its questions from, for legacy runs from 19 May 2026 on, the day that file last changed.

### 30. The answers under each question in the dashboard

**Now:** each question of a child shows the answer before and after searching, with the child's own rating as stars, or "Non lo so" (fixed during the rehearsal, see below). May's runs have no answer before searching. The dashboard reads these from the logs, so its first refresh after the deploy reads every log again, once.

### 31. The recap PDF for researchers

**Now:** where the child saved the activity, the run page and the participant page offer "Scarica il riepilogo finale del bambino (PDF)": the PDF the server kept. The dashboard finds it by the attempt ID in the answer events, and reads the children's database read-only.

### 32. May's experiment: theme and questions

**Now:** in Sessions, "Esperimento 19 maggio" shows its theme per class: India for the 3rd class (IDs 1-8, 17, 18), Spazio for the 4th (IDs 9-16), whose questions this year's 4th class has again. The class's data page for 2025/2026 lists the three questions. Both come from `data/user_topics.csv`.

| Before | After |
| --- | --- |
| ![Before](child_pages_2026-11/before-r3-dashboard-sessions.jpg) | ![After](child_pages_2026-11/after-r3-dashboard-sessions.jpg) |

![The 3rd class's May questions](child_pages_2026-11/after-r3-dashboard-may-class.jpg)

## Matthias's iPad check, 8 November

Matthias deployed fixes 23-32 and tried them on his iPad the same evening.

### 33. A dark ring around the ✕ as the pop-up opened

**Was:** the ✕ of "La mia prima risposta" opened with a dark ring drawn with a small animation, gone after a tap anywhere. The pop-up put the focus on the ✕ as it opened, and the browser drew its focus ring.
**Now:** the pop-up opens with the focus on its title. Tab still reaches the ✕, and Escape still closes the pop-up.

### 34. Recap cards out of the picture, lines hard to see

**Was:** some cards and magnifiers stuck out of the picture, as in the Figma. The dashed lines were black and disappeared on dark parts.
**Now:** every card and magnifier sits inside the picture. On orecchio the lines are dark with a light edge, on spazio white with a dark edge. The numbering stays as Diletta asked (fix 23).

### 35. "Cerca" right after the bar

**Was:** an empty space was kept between the bar and "Cerca" for the ✕ that clears the search.
**Now:** "Cerca" sits right after the bar. Once the child types, the ✕ appears between them; the bar gives it the room, so the row keeps its width and stays centred.

| Before | After, empty | After, typing |
| --- | --- | --- |
| ![Before](child_pages_2026-11/before-r3-search.jpg) | ![After](child_pages_2026-11/after-r3-search.jpg) | ![After](child_pages_2026-11/after-r3-search-typed.jpg) |

### 36. May's question on its run page

**Was:** "Recorded question: Question text was not recorded".
**Now:** the question May's app read for that ID and topic, next to the topic's name, with a note that it was not recorded in the log.

| Before | After |
| --- | --- |
| ![Before](child_pages_2026-11/before-r3-dashboard-may-run.jpg) | ![After](child_pages_2026-11/after-r3-dashboard-may-run.jpg) |

### 37. A child's statistics as one card per question

**Was:** one wide table, the answers squeezed into the first column and small notes under the numbers. Matthias found it chaotic.
**Now:** one card per question: the question, the answers before and after the search side by side, then one labelled value per figure. Under the cards, the PDF of the recap where there is one.

| May, before | May, after | A child of this year, after |
| --- | --- | --- |
| ![Before](child_pages_2026-11/before-r3-dashboard-may.jpg) | ![After](child_pages_2026-11/after-r3-dashboard-may.jpg) | ![After](child_pages_2026-11/after-r3-dashboard-tuesday.jpg) |

### Checks on this round

On the production image with a stand-in search and synthetic data, not on a real tablet. A first pass ran without May's synthetic logs, by a mistake in the rehearsal's setup; the second pass, with them, on `9dd8e89`, gives the figures for Monday, Tuesday, the exports and the dashboard.

| Check | Result |
| --- | --- |
| Monday: the setup tool on a fresh install, then Diletta enters the orecchio questions | Done; a second run is refused; nobody can start before Tuesday |
| Tuesday: both classes and the test IDs at once | 20 of 20 finished; no log damage in the real or the test folder; no test data among the real logs; nobody needed a second tap |
| Exports | Each class holds its own IDs, byte-identical to the logs, with May's records in their 2025/2026 classes; May's old logs unchanged |
| Dashboard | All 60 final answers under their question; all 20 recap PDFs identical to the server's; May's questions named, except one synthetic run of 18 May, older than the file, which keeps its number as intended |
| Server killed during a class of 20 | Back in 2.1 s, 20 of 20 finished, no log damage; the test runs alongside finished |
| 9 faults: offline, lost replies, reload, double taps and more | Nothing lost; the PDF kept on the server |
| Full test suite with browser tests | 1100 of 1101 passed. The other, in `test_student_security.py`, passed alone 3 of 3 and in its file 19 of 19; it is the test that failed once under load on 7 November, and this round does not change that page's HTML |

**Found by the rehearsal and fixed:** a child who chose "Non lo so" had no "Prima della ricerca" in the dashboard, because that answer is logged with no text (`9dd8e89`).

## Awkward use, tried on the production image

Each of these ran on the real pages in a browser, in WebKit, Chromium or both, with test IDs unless noted.

| Tried | Result |
| --- | --- |
| A 1500-character answer, one 500-character word, and code, quotes, emoji and new lines in an answer, on every page and in the PDF | Stays in its box, scrolls inside it, shown as plain text, nothing runs. An emoji prints as a black square in the PDF only; the pages and the log keep it |
| Questions of about 170 characters, entered in the editor, with a real ID at 1024 x 520 | Every step fits |
| Reload, Back and Forward at each step | Draft and stars kept, and one `TaskStarted` and one `TaskEnded` per question |
| Double taps on every button | Moves on once, with no repeated event |
| Conferma with nothing, with only spaces, and without stars | Refused; the text stays |
| The keyboard taking half the screen (1280 x 340, 1024 x 280) | Every button can be reached by scrolling |
| "Ricomincia" from every page of a test run | A new run, from the start |
| A clip that cannot load, and autoplay blocked | The still stays and the child can go on |
| Addresses typed by hand, with and without an ID | No server error |
| Upgrading from the version on the server, with a test run half way | The run continues; sessions, May's records and test logs stay |

**Small scroll left in place:** at 1024 x 520 the recap needs 4 px of scrolling with short answers, and up to 87 px with very long ones. Every button can still be reached.

## Noticed and left for Matthias

These change nothing in the logs. Each was left because it is a decision, or a change to a page that works, so close to the class.

- **A recap past the 60-minute limit.** Changes not saved by then are not kept, and the run gets no PDF. Keeping a child on the recap through a long break would need an exception to the limit or to the rule that hides the recap from a returning browser, so that a next child could see or change the answers. That is a flow decision. See fix 18.
- **The start page's error under load.** A child who gets "Salvataggio non disponibile" can try again, and that worked each time. Automatic retrying would change what the child sees. The server's log now gives the reason, so look there first if it happens.
- **A request that never finishes.** The recap's buttons stay disabled until the browser gives up on it. Reloading the page should clear it. Adding deadlines is a bigger change than this close to the class allows.
- **Events left in the browser.** A child who returns past the idle limit reaches a closing page that uploads nothing. On the real flow, tried on the production image, that left one `idSubmitted`, and the next child on that tablet recovered it into a side log. Events queued while offline would wait the same way.
- **Two tabs on one tablet.** If a second tab ends the session, "Chiudi" keeps saying "Salvataggio dei dati non disponibile" until the page is reloaded. Children use one tab.
- **Text typed before the page's script has started** is treated as already saved, and is lost unless the child types more. It is a narrow window, and untested. The simple fix could log edits that never happened, so it needs care.
- **Diletta's questions on the child pages.** Test IDs have their own fixed questions, and real IDs open only on the session's day, so she cannot see her own questions as a child before Tuesday. She can read them in the dashboard and check the clips through `TEST-orecchio`, whose three questions follow the same box order.
- **The charts "Nel corso delle sessioni"** on a child's page appear from the child's second session. May's experiment is not a session, so after Tuesday each child has a table with one row and no chart yet.
- **Emoji in the PDF** print as a black square. The pages and the log keep them.
- **Old external scripts on the search page** raise a browser error, `Cannot read properties of undefined (reading 'fn')`, which stopped nothing in any rehearsal. Removing them is a change to a page that works.

## What did not change

What is saved and logged, the search, the question order, the session rules, the dashboard's other pages, and the search page's layout apart from its font, its pop-up and the place of "Cerca" (fix 35).

## How to change things later

- **Logo:** replace `static/images/Logo.png`.
- **Theme texts:** `INTRO_TEXTS` in `student_progress.py`.
- **Where the cards sit on an animation:** the `.unlock--` rules in `static/study-review.css`, and `REVIEW_ARROWS` in `search_app.py`.
- **After changing a page's CSS, script or clip:** raise its `child-pages-N` where the pages load it, or tablets may keep the old file.
- **How long an idle connection stays open:** `--keep-alive` in `logger/search-app/Dockerfile`.
- **Where the recap's cards and arrows sit:** the `.recap-piece--` rules in `static/recap.css`, and `RECAP_ARROWS` in `student_recap.py`.
- **May's question names and themes in the dashboard:** `data/user_topics.csv`, and `THEMES` in `research_dashboard/legacy_topics.py`.
