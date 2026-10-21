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
- Evidence: screenshots and client events supplied. Screenshot
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
5. Compare with the original URL opened directly in a separate tab. The tester's
   direct-tab result is still pending.

The local Vertex credentials are missing, so these observations enter the viewer
through a direct URL after starting a task. They do not validate result-click
logging, return-to-results behavior or the complete search flow.

### Observed client events for Vikidia

The tester supplied these four events on 2026-10-21. Each event has the same
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

## Agreed handling

Pending discussion. Record the decision and its tracking limitations here.

Before choosing the fallback, confirm whether the study permits opening a resource
in a separate browser tab. External-tab navigation, rendering and reading time
cannot be inferred from a click on the app's outbound link.

## Regression checks

- Working resources still open.
- Viewer back and return-to-results navigation work.
- Query, result page, participant and task context are preserved.
- Existing non-reward logs remain intact.
- Load outcomes and tracking limitations are recorded accurately.
- Working and failing examples are checked in Brave on a real iPad
  and available desktop devices.
