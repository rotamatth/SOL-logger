# Iframe loading investigation

Branch: samuele/iframe-loading
PR target: samuele-dev

## Goal

Investigate resource pages that fail inside the viewer in Brave.
Agree on handling for failures and pages that cannot be embedded.

## Reproduction records

Record one entry per URL and device:
- App URL, commit and reproduction steps:
- Requested resource URL:
- Device/model:
- OS and Brave versions:
- Brave Shields settings:
- Redirect chain and final URL, where observable:
- Outcome inside the viewer:
- Outcome when opened directly:
- Console/network evidence:
- Resource load and tracking events:
- Screenshot references:

### Brave on Windows, 2026-10-21

- App: `http://localhost:7001`, commit
  `0491c91b05ba7d514c034840c10255ca25a90136`.
- Browser/device: Brave on a Windows PC.
- Exact device model, Windows/Brave versions and Shields settings: pending.
- Evidence: screenshots and recorded client events. Screenshot
  files and browser console/network captures have not yet been added to the PR.

| Resource | Visible browser outcome | Diagnostic evidence |
| --- | --- | --- |
| https://it.wikipedia.org/wiki/Gange | Article visible inside the viewer. | A separate Python GET returned HTTP 403; this did not describe the browser's visible outcome. |
| https://www.focus.it/scienza/spazio/avvistati-i-satelliti-di-giove | Article visible inside the viewer. | Python GET: HTTP 200, no redirects, no X-Frame-Options or frame-ancestors directive observed. |
| https://it.vikidia.org/wiki/Foce | Viewer displays "Connessione negata da it.vikidia.org". | Python HEAD/GET: HTTP 200, no redirects, X-Frame-Options: SAMEORIGIN. The app probe reports blocked=true with reason x-frame-options:sameorigin. |

These diagnostic requests are separate from the browser's document requests.
Browser response headers, redirects and direct-tab outcome still need to be
captured. No iPad or macOS result is established by these observations.

### Reproduce the Vikidia failure

1. Open `http://localhost:7001/welcome` in Brave and start a local test participant.
2. Continue through the task introduction and enter the search page.
3. In that same tab, enter:

   ```text
   http://localhost:7001/webpage?url=https%3A%2F%2Fit.vikidia.org%2Fwiki%2FFoce&query=Gange&page=1
   ```

4. Record the viewer outcome, browser Console/Network evidence and client events.
5. Compare with the original URL opened directly in a separate tab. The
   direct-tab result is still pending.

The local Vertex credentials are missing, so these observations enter the viewer
through a direct URL after starting a task. They do not validate result-click
logging, return-to-results behavior or the complete search flow.

### Observed client events for Vikidia

These four events were recorded on 2026-10-21. Each event has the same
`uid` (`13`) and `sessionID`; the unique session identifier is omitted here.
All timestamps use the logger's Europe/Zurich format without an offset.

| Timestamp | Event | Relevant fields |
| --- | --- | --- |
| 2026-10-21T21:33:37.563 | webpageOpened | url=https://it.vikidia.org/wiki/Foce |
| 2026-10-21T21:33:37.564 | resourceViewStarted | Same URL; windowLocation identifies the viewer URL above. |
| 2026-10-21T21:33:37.828 | iframeNavigationTrackingLimited | reason=cross-origin-access-blocked |
| 2026-10-21T21:33:39.420 | webpageLoadFailed | reason=x-frame-options:sameorigin |

This excerpt establishes consistent participant/session identifiers across these
four events. It does not validate task identity, close-event pairing, dwell time,
back navigation or other existing logs. No close event is expected in an excerpt
captured while the viewer remains open.

## Findings

1. The observed Vikidia refusal is consistent with its `SAMEORIGIN` embedding
   policy: the local app and Vikidia have different origins. See
   [RFC 7034](https://www.rfc-editor.org/rfc/rfc7034).
2. In the current implementation, `webpageLoadFailed` is selected from the
   server-side `/iframe_check` response. It is not a direct browser error signal.
   The screenshot separately establishes the visible failure for this example.
3. `iframeNavigationTrackingLimited` records inability to inspect the frame URL.
   It must not be treated as proof of a load failure: readable content and
   cross-origin tracking restrictions are separate observations.
4. An iframe `load` event alone is not proof that the resource displayed
   successfully. See the [iframe load/error behavior documentation](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe#error_and_load_event_behavior).
5. Python diagnostic responses and browser outcomes can differ, as shown by the
   Wikipedia control. Header probes must retain their status as diagnostic
   evidence rather than guaranteeing the browser's load outcome.

A second candidate is
`https://pwg.gsfc.nasa.gov/stargaze/Iiomoons.htm`: a diagnostic GET returned
HTTP 200 with `frame-ancestors 'self' *.gsfc.nasa.gov`. Browser reproduction is
still pending; this is not yet a second observed failure.

## Options for reviewer discussion on 2026-10-22

Decision status: pending discussion. The alternatives below describe possible
approaches and how to implement each one. No implementation has been agreed.
The existing viewer renders external pages in an iframe.

### What can be shown inside the app?

The original page can be embedded when the publisher's policies permit the app's
origin. A parent page cannot override a third-party X-Frame-Options or
frame-ancestors restriction using its own JavaScript. See
[X-Frame-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options)
and [frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors).

A reader or proxy serves a different representation through infrastructure we
control. That distinction affects presentation, navigation and interpretation of
the study logs, even when the original article text is preserved.

| Option | Feasibility and coverage | Main trade-off for the study |
| --- | --- | --- |
| Reader for Vikidia or another explicitly supported source | Promising for Vikidia: article retrieval through its API has been verified below. Each additional source needs a supported retrieval/rendering path. | Keeps participants in the app and permits instrumentation of the reader, but changes layout and may omit scripts, advertisements, interactive features or unsupported media. |
| Reader for arbitrary search results | Best-effort coverage; feasibility depends on the source. An adapter that works for Vikidia does not establish support for unrelated publishers. | Inconsistent extraction and presentation can change the task experience and require ongoing source-specific maintenance. |
| Full-page reverse proxy | Possible for selected pages, with substantial integration complexity. Universal compatibility cannot be promised. | Relative URLs, redirects, cookies, scripts and navigation may need adaptation. Untrusted publisher scripts must be isolated from the study application's origin and data. |
| Explicit recovery UI: external tab or another resource | Technically straightforward, subject to agreement on the study workflow. | An external tab preserves the publisher's page, but its rendering, navigation and reading time are not observable by the app. Choosing another resource keeps the participant in the app but changes which source is used. |

The cross-origin tracking distinction is described in the
[same-origin policy documentation](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy).

### Option 1: reader for Vikidia or another supported source

Retrieve article content through a source-specific adapter and display a clearly
identified reading view inside the app. This preserves the article content where
supported, but does not reproduce the original publisher page.

How to implement it:

1. Define the supported hosts and article URL formats. For Vikidia, convert the
   article URL into parameters for the fixed MediaWiki API endpoint instead of
   fetching any URL supplied by the client.
2. Retrieve the article HTML on the backend. Handle missing pages, API errors,
   article redirects, request timeouts and response-size limits.
3. Sanitize the HTML with a maintained allowlist sanitizer. Remove executable or
   unsupported elements and attributes, normalize supported image/link URLs,
   retain source attribution and check the source's reuse conditions.
4. Render a reader template with the original source URL and a reading-view label.
   Route supported article links through the adapter; send unsupported links to
   the agreed recovery flow.
5. Integrate navigation and logging using the shared requirements below. If
   retrieval or rendering fails, offer recovery without showing incomplete
   content as a successful article load.

#### Verified feasibility check: Vikidia API

On 2026-10-21, a read-only request to
`https://it.vikidia.org/w/api.php` with the following parameters returned HTTP 200
and a JSON response containing the article HTML:

```text
action=parse
page=Foce
prop=text|displaytitle
format=json
formatversion=2
```

- Returned article: `Foce`, page ID `25738`.
- Returned HTML length: `7722` characters.
- API error field: absent.
- Scope of this result: article retrieval from this endpoint for this example.
  Reader UI, sanitization, image/link handling, reuse conditions and Brave/iPad
  rendering have not yet been evaluated by this check.

MediaWiki documents this retrieval mechanism in
[API:Parsing wikitext](https://www.mediawiki.org/wiki/API:Parsing_wikitext).

### Option 2: reader across unrelated search results

Fetch HTML on the backend and extract the main article into a shared reading
view. Coverage is best effort: some pages require JavaScript, authentication or
source-specific extraction, and some cannot be retrieved at all.

How to implement it:

1. Choose a representative set of failing URLs and working controls. Define what
   counts as a usable extraction, including title, article text and required
   images. Establish coverage on this sample before expanding support.
2. Build a bounded backend retrieval service. Validate the requested URL, every
   redirect and any fetched resource; restrict network destinations, response
   sizes, content types and request duration.
3. Apply a maintained main-content extractor, then sanitize its output before
   rendering it. Use source-specific adapters where generic extraction fails.
   Retain attribution and the original URL, and check source reuse conditions.
4. Detect empty, error or unusable extraction results and offer recovery. Do not
   mark an HTTP 200 response or non-empty HTML as proof of a usable article.
5. Reuse the reader navigation and logging integration from option 1. Record
   which extraction path was used and maintain regression examples for each
   supported source. Do not promise support for every search result.

### Option 3: full-page reverse proxy for selected sources

Retrieve the page and its resources through controlled infrastructure, adapting
them for display through the proxy. This can preserve more of a page's visual
layout than a reader, but scripts, sessions and navigation make compatibility
source-dependent. It is not a way for parent-page JavaScript to override the
original site's embedding policy.

How to implement it:

1. Limit the first implementation to an explicit list of sources and public,
   unauthenticated pages. Select representative pages and required interactions
   before deciding whether the approach is suitable.
2. Serve proxied content on an isolated origin without the app's session cookies
   or credentials. Define a sandbox and script policy before enabling active
   third-party content.
3. Implement bounded retrieval for documents and assets, validating each
   destination and redirect. Rewrite relative links, image and stylesheet URLs,
   redirects and supported navigation so they resolve through the intended path.
4. Define response headers for the proxy's own representation and assess CSP,
   scripts, forms, cookies and cross-origin requests for each supported source.
   Changing the proxy response does not change the original site's policy.
5. Route unsupported behavior to recovery and preserve the source URL separately
   from proxy URLs in logs. Validate appearance, navigation and isolation on the
   actual target browsers before expanding coverage.

### Option 4: explicit recovery in the viewer

Keep the existing iframe and offer a clear path when a page is unavailable or
its load status cannot be established. The alternatives are opening the original
page in an external tab or returning to results to choose another resource.
This option does not display a blocked page inside the app.

How to implement it:

1. Add an accessible recovery control in the viewer, including when automatic
   checks are inconclusive. Distinguish a reported embedding restriction from
   an unknown load outcome; a timeout or cross-origin access error alone does
   not prove that the page failed.
2. If external navigation is accepted for the study, provide an explicit link to
   the validated original URL using `target="_blank"` and
   `rel="noopener noreferrer"`. Let the participant choose to open it.
3. Keep the app's participant/task and search context available when returning.
   If external tabs are excluded, offer return to results and another resource.
4. Record the external-link action separately from page load and resource view
   events. The app cannot confirm that the external page loaded, observe its
   navigation or measure reading time there.
5. Check successful iframes, blocked pages, unknown outcomes, return navigation
   and duplicate-event prevention before considering the flow ready.

### Shared integration and validation

- Preserve working iframe pages and agree on when an alternative becomes
  available. A cross-origin tracking restriction is not a reason by itself to
  replace a working page.
- Keep participant/task identity, query and result-page context. Define both
  navigation between adapted articles and return to the search results.
- Distinguish iframe, reader, proxy and external-link intent in logs. Keep the
  original source URL separate from the app URL. Separate diagnostic probe
  results, observable load outcomes, unknown status and tracking limitations.
- Agree on compatibility of existing event names and fields before changing
  their meaning. Preserve existing non-reward logs and pair resource start/end
  events once per view. Viewer dwell time is not verified reading time.
- For a reader or proxy, the current `_is_safe_iframe_url` helper combined with
  unrestricted redirect following is not a complete retrieval policy. Apply
  validation to every request, redirect and fetched resource.
- Add focused tests for the chosen option: successful and failed retrieval,
  redirects, unsafe markup/URLs, timeouts, navigation/context and logging.
  Repeat the Wikipedia/Focus controls and Vikidia failure in Brave on real target
  devices, including iPad, capturing versions, Shields settings, screenshots and
  logs. Keep the PR as a draft until the affected flow and logging are checked.

Current validation prerequisites: the local preview needs working Vertex
credentials to check the complete search/result-click/return flow. Its current
loopback address is reachable only from the Windows machine; iPad validation
needs a test environment reachable from that device.

Likely change areas, subject to the chosen design:

- `logger/search-app/templates/webpage.html`: recovery controls and viewer state.
- `logger/search-app/search_app.py`: viewer/probe integration and phase/context guards.
- A source adapter and reader template: API retrieval and adapted presentation,
  kept separate from the existing route module where practical.
- `logger/search-app/static/logger.js`, logging checks and documentation:
  event compatibility and explicit rendering/tracking semantics.
- `logger/search-app/tests/`: focused behavior tests and relevant existing
  logging/back-navigation regressions.

Recommendation for discussion: retain working iframes, agree on an explicit
recovery path for all unsupported/unknown cases, and consider a Vikidia-only
reader if the study accepts adapted content. Broader reader coverage or a
full-page proxy should have a separately bounded scope.

### Decisions to take with the reviewer

- Must participants see the original publisher presentation, or is a clearly
  identified reading view acceptable for this study?
- Is support limited to an agreed list of sources, or expected for every search
  result? Which examples define acceptable coverage?
- May a participant open an external tab? If not, what is the in-app path when a
  resource cannot be embedded or adapted?
- Which navigation, duration and interaction metrics are required, and which
  tracking limitations are acceptable? How will existing log consumers handle
  clarified load-event semantics?
- Which exact iPad/Brave and desktop/Brave versions will be available for final
  validation? Is a Mac target available?
- Should the initial PR include a Vikidia reader, or cover recovery and logging
  only? Should broader source coverage be handled separately?

## Agreed handling

Pending discussion. Record the decision and its tracking limitations here.

- Decision/date/reviewer: pending.
- Chosen option and supported sources: pending.
- Recovery when embedding/adaptation fails: pending.
- Agreed logging semantics and limitations: pending.
- Required device matrix and acceptance checks: pending.

## Regression checks

- Working resources still open.
- Viewer back and return-to-results navigation work.
- Query, result page, participant and task context are preserved.
- Existing non-reward logs remain intact.
- Load outcomes and tracking limitations are recorded accurately.
- Working and failing examples are checked in Brave on a real iPad
  and available desktop devices.
