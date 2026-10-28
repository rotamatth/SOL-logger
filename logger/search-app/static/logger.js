(() => {


    // Fallback-UUID-Function for outdated browsers
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            const r = Math.random() * 16 | 0,
                  v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    const LOG_TIME_ZONE = "Europe/Zurich";

    function padNumber(value, width = 2) {
        return String(value).padStart(width, "0");
    }

    function getZonedParts(date, timeZone) {
        const formatter = new Intl.DateTimeFormat("en-CA", {
            timeZone,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
            hourCycle: "h23"
        });

        const parts = {};
        formatter.formatToParts(date).forEach(part => {
            if (part.type !== "literal") {
                parts[part.type] = Number(part.value);
            }
        });
        return parts;
    }

    function formatSwissTimestamp(date = new Date()) {
        const parts = getZonedParts(date, LOG_TIME_ZONE);
        const milliseconds = date.getMilliseconds();

        return `${parts.year}-${padNumber(parts.month)}-${padNumber(parts.day)}`
            + `T${padNumber(parts.hour)}:${padNumber(parts.minute)}:${padNumber(parts.second)}`
            + `.${padNumber(milliseconds, 3)}`;
    }

    function safeParseArray(rawValue) {
        if (!rawValue) return [];
        try {
            const parsed = JSON.parse(rawValue);
            return Array.isArray(parsed) ? parsed : [];
        } catch (err) {
            console.warn("Failed to parse stored logger data:", err);
            return [];
        }
    }

    function createClientSessionID() {
        return (typeof crypto !== 'undefined' && crypto.randomUUID)
            ? crypto.randomUUID()
            : generateUUID();
    }

    const logger = {
        sessionID: null,
        logs: [],
        historyTracker: [],

        init() {
            const serverID = (typeof window !== 'undefined' && window.SESSION_ID) ? window.SESSION_ID : '';
            const storedSessionID = localStorage.getItem('sessionID');
            const storedLogs = safeParseArray(localStorage.getItem('sessionLogs'));
            const browserHistory = safeParseArray(localStorage.getItem('browserHistory'));
            let logsToRestore = storedLogs;
            let historyToRestore = browserHistory;

            if (serverID) {
                this.sessionID = serverID;
                if (storedSessionID && storedSessionID !== serverID) {
                    const currentUser = window.USER_ID || null;
                    logsToRestore = storedLogs.filter(entry => {
                        return entry
                            && entry.type === "idSubmitted"
                            && entry.uid
                            && entry.uid === currentUser;
                    });
                    historyToRestore = [];
                }
                logsToRestore = logsToRestore.map(entry => ({
                    ...entry,
                    sessionID: this.sessionID
                }));
                localStorage.setItem('sessionID', this.sessionID);
                localStorage.setItem('sessionLogs', JSON.stringify(logsToRestore));
                localStorage.setItem('browserHistory', JSON.stringify(historyToRestore));
            } else {
                this.sessionID = storedSessionID || createClientSessionID();
                localStorage.setItem('sessionID', this.sessionID);
            }

            this.logs = logsToRestore;
            this.historyTracker = historyToRestore;
        },

        clearClientData(options = {}) {
            const preserveSessionID = options.preserveSessionID === true;
            const createNewSessionID = options.createNewSessionID === true;
            const nextSessionID = preserveSessionID
                ? this.sessionID
                : (createNewSessionID ? createClientSessionID() : null);

            localStorage.clear();
            if (typeof sessionStorage !== 'undefined') {
                sessionStorage.clear();
            }

            this.logs = [];
            this.historyTracker = [];
            this.sessionID = nextSessionID;

            if (nextSessionID) {
                localStorage.setItem('sessionID', nextSessionID);
            }
        },
        
        logEvent(type, details = {}) {
            if (typeof window !== 'undefined'
                && window.taskEndLockout
                && type !== "ClickedEndTaskConfirmation"
                && type !== "TaskEnded"
                && type !== "browserBackBlocked"
                && type !== "resourceViewEnded") {
                return;
            }
            const event = {
                type,
                timestamp: formatSwissTimestamp(),
                sessionID: this.sessionID,
                uid: window.USER_ID || null,
                ...(window.STUDY_PROGRESS_CONTEXT || {}),
                ...details
            };
            console.log("[LOG]", event);
            this.logs.push(event);
            localStorage.setItem('sessionLogs', JSON.stringify(this.logs));
        },

        addHistory(url) {
            this.historyTracker.push(url);
            localStorage.setItem('browserHistory', JSON.stringify(this.historyTracker));
        },

        checkHistory(url) {
            if (this.historyTracker.length <= 1) return;
            
            const prevPage = this.historyTracker[this.historyTracker.length - 2];
            if (url==prevPage) return this.historyTracker[this.historyTracker.length - 1];
            else return;
        },

        removeHistory(){
            this.historyTracker.splice(this.historyTracker.length-2, 2);
            localStorage.setItem('browserHistory', JSON.stringify(this.historyTracker));
        },

        getHistory() {
            return JSON.stringify(this.historyTracker);
        },

        sendLogs() {
            if (this.uploadInFlight) return this.uploadInFlight;
            const pendingKey = `solPendingUpload:${this.sessionID}`;
            let pending;
            try { pending = JSON.parse(localStorage.getItem(pendingKey) || 'null'); }
            catch (_) { return Promise.reject(new Error('Pending upload is unreadable; keep this browser open.')); }
            if (!pending && this.logs.length === 0) return Promise.resolve();
            if (!pending) {
                pending = {session_id: this.sessionID, batch_id: createClientSessionID(), logs: this.logs.slice()};
                // Persist the exact request before sending it. A lost response or
                // page reload must retry the same batch, including its identifier.
                try { localStorage.setItem(pendingKey, JSON.stringify(pending)); }
                catch (error) { return Promise.reject(error); }
            }
            const body = JSON.stringify(pending);
            this.uploadInFlight = fetch('/log_session', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body,
                // A small batch may finish after the page closes (browsers cap
                // keepalive bodies at 64 KiB). Otherwise the next page retries it.
                keepalive: new Blob([body]).size < 60000
            }).then(async response => {
                if (!response.ok) {
                    throw new Error('Failed to send logs.');
                }
                const data = await response.json();
                if (data.status !== 'logged' || data.batch_id !== pending.batch_id) {
                    throw new Error('Upload acknowledgement does not match the pending batch.');
                }
                console.log('Logs successfully sent to server.');
                // Events added while the request was in flight must remain queued.
                const prefix = this.logs.slice(0, pending.logs.length);
                if (JSON.stringify(prefix) === JSON.stringify(pending.logs)) {
                    this.logs.splice(0, pending.logs.length);
                }
                localStorage.setItem('sessionLogs', JSON.stringify(this.logs));
                localStorage.removeItem(pendingKey);
                // The navigation history stays: uploads now also happen during a
                // task, and logSERP uses it to tell a revisited results page from
                // a new one. Ending a task clears all client data, history included.
                // The server may have recovered events left behind by a
                // previous, unfinished participant and saved them as an
                // incomplete experiment. Surface that to the operator.
                    const recovered = data && data.recovered_incomplete;
                    if (recovered && typeof recovered === 'object'
                        && Object.keys(recovered).length > 0
                        && typeof window !== 'undefined'
                        && typeof window.dispatchEvent === 'function') {
                        window.dispatchEvent(new CustomEvent('sol:incomplete-recovered', {
                            detail: { recovered }
                        }));
                    }
                    return response;
            }).finally(() => {
                this.uploadInFlight = null;
            }).then(async response => {
                if (this.logs.length) await this.sendLogs();
                return response;
            });
            return this.uploadInFlight;
        }
    };

    logger.init();
    window.studyLogger = logger;
})();

const BROWSER_BACK_BLOCKER_HISTORY_DEPTH = 10;
const BROWSER_BACK_BLOCKER_GUARD_STATE_KEY = "__solBrowserBackBlockerGuard";
const BROWSER_BACK_BLOCKER_BASE_STATE_KEY = "__solBrowserBackBlockerBase";
const LAST_ALLOWED_APP_URL_SESSION_KEY = "solLastAllowedAppUrl";

window.__SOLBrowserBackRecoveryInProgress = false;
let browserBackBarrierArmedUrl = null;

function getCurrentWindowUrl() {
    return window.location?.href || window.location?.origin || "";
}

function getCurrentWindowPathname() {
    return window.location?.pathname || "";
}

function getPageNavigationType() {
    const entries = window.performance?.getEntriesByType?.("navigation") || [];
    return entries[0]?.type || "";
}

function isSameOriginUrl(url) {
    if (!url) return false;
    try {
        return new URL(url, getCurrentWindowUrl()).origin === window.location.origin;
    } catch (_) {
        return false;
    }
}

function getLastAllowedAppUrl() {
    try {
        return sessionStorage.getItem(LAST_ALLOWED_APP_URL_SESSION_KEY);
    } catch (_) {
        return null;
    }
}

function storeLastAllowedAppUrl() {
    const currentUrl = getCurrentWindowUrl();
    if (!currentUrl) return;
    try {
        sessionStorage.setItem(LAST_ALLOWED_APP_URL_SESSION_KEY, currentUrl);
    } catch (_) {}
}

function buildBrowserBackBlockerHistoryState(extraState = {}) {
    const currentState = window.history?.state;
    const safeCurrentState = (
        currentState && typeof currentState === "object" && !Array.isArray(currentState)
    ) ? currentState : {};

    return {
        ...safeCurrentState,
        ...extraState,
        solUrl: getCurrentWindowUrl()
    };
}

function logNativeBrowserBackBlocked(reason, targetURL = null) {
    if (!window.studyLogger) return;
    const fromURL = getCurrentWindowUrl();
    const toURL = targetURL || fromURL;
    window.studyLogger.logEvent("browserBackBlocked", {
        url: fromURL,
        pathname: getCurrentWindowPathname(),
        fromURL,
        toURL,
        reason,
        targetURL,
        navigationType: getPageNavigationType()
    });
}

function armBrowserBackHistoryBarrier(force = false) {
    if (!window.history?.replaceState || !window.history?.pushState) return;

    const currentUrl = getCurrentWindowUrl();
    if (!force && browserBackBarrierArmedUrl === currentUrl) return;

    try {
        window.history.replaceState(
            buildBrowserBackBlockerHistoryState({
                [BROWSER_BACK_BLOCKER_BASE_STATE_KEY]: true
            }),
            "",
            currentUrl
        );

        for (let index = 0; index < BROWSER_BACK_BLOCKER_HISTORY_DEPTH; index += 1) {
            window.history.pushState(
                buildBrowserBackBlockerHistoryState({
                    [BROWSER_BACK_BLOCKER_GUARD_STATE_KEY]: true,
                    browserBackBlockerGuardIndex: index
                }),
                "",
                currentUrl
            );
        }
        browserBackBarrierArmedUrl = currentUrl;
    } catch (err) {
        console.warn("Failed to arm browser back blocker:", err);
    }
}

function getRecoveryUrlForNativeBackNavigation(event = null) {
    const lastAllowedUrl = getLastAllowedAppUrl();
    const currentUrl = getCurrentWindowUrl();
    const navigationType = getPageNavigationType();
    const isBackForwardNavigation = Boolean(event?.persisted) || navigationType === "back_forward";

    if (!isBackForwardNavigation) return null;
    if (!lastAllowedUrl || lastAllowedUrl === currentUrl) return null;
    if (!isSameOriginUrl(lastAllowedUrl)) return null;

    return lastAllowedUrl;
}

function redirectNativeBackNavigationToLastAllowedUrl(reason, event = null) {
    const targetURL = getRecoveryUrlForNativeBackNavigation(event);
    if (!targetURL) return false;

    window.__SOLBrowserBackRecoveryInProgress = true;
    logNativeBrowserBackBlocked(reason, targetURL);

    try {
        window.location.replace(targetURL);
    } catch (err) {
        console.warn("Failed to recover from native browser back:", err);
    }
    return true;
}

function installNativeBrowserBackBlocker() {
    if (!window.history?.replaceState || !window.history?.pushState) return;

    window.addEventListener("popstate", () => {
        logNativeBrowserBackBlocked("popstate", getCurrentWindowUrl());
        armBrowserBackHistoryBarrier(true);
        storeLastAllowedAppUrl();
    });

    window.addEventListener("pageshow", (event) => {
        if (redirectNativeBackNavigationToLastAllowedUrl("pageshow", event)) return;

        window.__SOLBrowserBackRecoveryInProgress = false;
        storeLastAllowedAppUrl();
        armBrowserBackHistoryBarrier();
    }, true);

    if (redirectNativeBackNavigationToLastAllowedUrl("back-forward-load")) return;

    storeLastAllowedAppUrl();
    armBrowserBackHistoryBarrier();
}

installNativeBrowserBackBlocker();

const idform = document.getElementById("enter-id-form");
if (idform) {
  idform.addEventListener("submit", (e) => {
    if (e.defaultPrevented) return;
    const uid = document.getElementById("id-box")?.value || "";
    studyLogger.clearClientData({ createNewSessionID: true });
    studyLogger.logEvent("idSubmitted", { uid });
  });
}

const taskbtn = document.getElementById("task-btn")
if (taskbtn) {
    taskbtn.addEventListener("click", () => {
        studyLogger.logEvent("TaskStarted");
    });
}

const searchbox = document.getElementById("search-box");
let lastAutocompleteSelection = null;

function getAutocompleteSuggestions() {
    return Array.isArray(window.autoCompleteSuggestions)
        ? window.autoCompleteSuggestions
        : [];
}

function getAutocompleteContext() {
    const context = window.autocompleteContext || {};
    const suggestions = Array.isArray(context.suggestions)
        ? context.suggestions
        : getAutocompleteSuggestions();

    return {
        autocompletePrefix: typeof context.prefix === "string" ? context.prefix : "",
        autocompleteSuggestions: suggestions,
        autocompleteSource: context.source || "none",
        autocompleteQueryModel: context.queryModel || null
    };
}

function getAutocompleteSelectedSuggestion(value) {
    const selectedSuggestion = (value || "").trim();
    if (!selectedSuggestion) return null;
    return getAutocompleteSuggestions().includes(selectedSuggestion)
        ? selectedSuggestion
        : null;
}

function getAutocompleteLogContext(value = null) {
    return {
        ...getAutocompleteContext(),
        autocompleteSelectedSuggestion: getAutocompleteSelectedSuggestion(value)
    };
}

function logAutocompleteSelection(value, trigger) {
    const selectedSuggestion = (value || "").trim();
    if (!selectedSuggestion) return;
    if (!getAutocompleteSuggestions().includes(selectedSuggestion)) return;
    if (lastAutocompleteSelection === selectedSuggestion) return;

    lastAutocompleteSelection = selectedSuggestion;
    studyLogger.logEvent("choseAutoCompleteSuggestion", {
        query: searchbox?.value || "",
        selectedSuggestion,
        trigger,
        ...getAutocompleteLogContext(selectedSuggestion)
    });
}

if (searchbox) {
    searchbox.addEventListener("focus", () => {
        studyLogger.logEvent("queryBoxFocused");
    });

    searchbox.addEventListener("change", () => {
        logAutocompleteSelection(searchbox.value, "change");
    });

    searchbox.addEventListener("input", () => {
        if (searchbox.value.trim() !== lastAutocompleteSelection) {
            lastAutocompleteSelection = null;
        }
    });
}

const querySuggestionsList = document.getElementById("query-suggestions");
if(querySuggestionsList){
    querySuggestionsList.addEventListener("mouseover", (e) => {
    const suggestionElement = e.target.closest("li") || e.target.closest("option");
    if (!suggestionElement) return;

    studyLogger.logEvent("hoverOverQuerySuggestions", {
            query: searchbox?.value || "",
            hoveredSuggestion: suggestionElement.value || suggestionElement.textContent,
        });
    });
    
    querySuggestionsList.addEventListener("pointerdown", (e) => {
        const suggestionElement = e.target.closest("li") || e.target.closest("option");
        if (!suggestionElement) return;

        logAutocompleteSelection(suggestionElement.value || suggestionElement.textContent, "pointerdown");
    });

}


const searchbar = document.getElementById("search-bar")
if (searchbar) {
    let querySubmitInProgress = false;
    let submittedQuery = "";
    searchbar.addEventListener("submit", (e) => {
        const query = document.getElementById("search-box")?.value || "";
        if (querySubmitInProgress && submittedQuery === query) {
            e.preventDefault();
            e.stopImmediatePropagation();
            return;
        }

        flushActiveResultExposures("new-search");
        logAutocompleteSelection(query, "submit");
        querySubmitInProgress = true;
        submittedQuery = query;
        studyLogger.logEvent("querySubmitted", {
            query,
            rawQuery: query,
            sanitizedQuery: query,
            ...getAutocompleteLogContext(query)
        });
    });

    window.addEventListener("pageshow", () => {
        querySubmitInProgress = false;
        submittedQuery = "";
    });
}

function getSearchAppLocation(query, page){
    const search_params = new URLSearchParams();
    search_params.set("query", query);
    search_params.set("page", page);
    return window.location.origin + "/result?" + search_params.toString();
}

function getCurrentSearchContext() {
    const panel = document.querySelector(".serp-panel");
    const firstResult = document.querySelector("article.content-section");
    const query = firstResult?.getAttribute("query")
        || panel?.dataset.sanitizedQuery
        || "";
    const page = firstResult?.getAttribute("page")
        || panel?.dataset.page
        || "";
    const rawQuery = firstResult?.dataset.rawQuery
        || panel?.dataset.rawQuery
        || query;
    const sanitizedQuery = firstResult?.dataset.sanitizedQuery
        || panel?.dataset.sanitizedQuery
        || query;

    return { query, rawQuery, sanitizedQuery, page };
}

function getPageType(url) {
    if (!url) return "unknown";
    try {
        const parsed = new URL(url, window.location.origin);
        if (parsed.pathname === "/webpage") return "webpage";
        if (parsed.pathname === "/result") return "serp";
        if (parsed.pathname === "/search") return "search";
        return "other";
    } catch (err) {
        return "unknown";
    }
}

function getReturnMetadata(fromURL, toURL) {
    const fromPageType = getPageType(fromURL);
    const toPageType = getPageType(toURL);
    let returnType = "other";
    if (fromPageType === "webpage" && toPageType === "serp") {
        returnType = "resource-to-serp";
    } else if (fromPageType === "serp" && toPageType === "serp") {
        returnType = "serp-to-serp";
    }

    return { fromPageType, toPageType, returnType };
}

function getBackButtonNavigationDetails(button, fallbackFromPageType) {
    const fromURL = window.location.href;
    const toURL = button?.href || button?.getAttribute?.("href") || "";
    const metadata = getReturnMetadata(fromURL, toURL);

    return {
        ...metadata,
        fromPageType: fallbackFromPageType || metadata.fromPageType,
        url: fromURL,
        fromURL,
        toURL
    };
}

function getTargetPage(label, current, link = null) {
    const href = link?.href || link?.getAttribute?.("href") || "";
    if (href) {
        try {
            const targetPage = parseInt(new URL(href, window.location.origin).searchParams.get("page"), 10);
            if (!isNaN(targetPage)) return targetPage;
        } catch (err) {
            // Fall back to label parsing below.
        }
    }

    const normalizedLabel = label.toLowerCase();
    if (normalizedLabel.includes("next") || normalizedLabel.includes("successiva") || label.includes("»")) return current + 1;
    if (normalizedLabel.includes("previous") || normalizedLabel.includes("precedente") || label.includes("«")) return current - 1;

    const num = parseInt(label, 10);
    return isNaN(num) ? null : num;
}

function getResultRank(element) {
    return element?.getAttribute("result_rank") || element?.id?.split("-").pop();
}

function getResultElements(rank) {
    const result = document.getElementById(`result-${rank}`);
    const link = document.getElementById(`abstract-link-${rank}`);
    const preview = document.getElementById(`abstract-preview-${rank}`);
    return { result, link, preview };
}

function getResultDetails(rank) {
    const { result, link, preview } = getResultElements(rank);

    if (!result || !link) {
        console.warn(`Missing required result logging hook for rank ${rank}.`);
        return null;
    }

    const query = result.getAttribute("query") || "";
    const rawQuery = result.dataset.rawQuery || query;
    const sanitizedQuery = result.dataset.sanitizedQuery || query;
    const docid = result.getAttribute("base_ir") || "";
    const page = result.getAttribute("page") || "";
    const navigationUrl = link.href || link.getAttribute("href") || "";
    const resultUrl = link.dataset.originalUrl || navigationUrl;

    return {
        query,
        rawQuery,
        sanitizedQuery,
        docid,
        rank: String(rank),
        page,
        title: link.textContent || "",
        snippet: preview?.textContent || "",
        url: resultUrl,
        navigationUrl,
        windowLocation: getSearchAppLocation(query, page),
    };
}

const RESULT_EXPOSURE_THRESHOLD = 0.5;
const RESULT_EXPOSURE_MIN_MS = 250;
const activeResultExposures = new Map();
let resultExposureObserver = null;

function exposureLogDetails(details) {
    return {
        query: details.query,
        rawQuery: details.rawQuery,
        sanitizedQuery: details.sanitizedQuery,
        docid: details.docid,
        rank: details.rank,
        page: details.page,
        url: details.url,
        windowLocation: details.windowLocation,
    };
}

function startResultExposure(result) {
    const rank = result.id.split("-")[1];
    if (activeResultExposures.has(rank)) return;

    const details = getResultDetails(rank);
    if (!details) return;

    const record = {
        rank,
        details,
        startedAt: Date.now(),
        startLogged: false,
        timer: null
    };
    record.timer = setTimeout(() => {
        const activeRecord = activeResultExposures.get(rank);
        if (!activeRecord || activeRecord.startLogged) return;
        studyLogger.logEvent("resultExposureStarted", exposureLogDetails(activeRecord.details));
        activeRecord.startLogged = true;
    }, RESULT_EXPOSURE_MIN_MS);

    activeResultExposures.set(rank, record);
}

function endResultExposure(rank, exitReason) {
    const record = activeResultExposures.get(rank);
    if (!record) return;

    activeResultExposures.delete(rank);
    if (record.timer) {
        clearTimeout(record.timer);
    }

    const durationMs = Date.now() - record.startedAt;
    if (durationMs < RESULT_EXPOSURE_MIN_MS) return;

    if (!record.startLogged) {
        studyLogger.logEvent("resultExposureStarted", exposureLogDetails(record.details));
    }
    studyLogger.logEvent("resultExposureEnded", {
        ...exposureLogDetails(record.details),
        durationMs,
        exitReason
    });
}

function flushActiveResultExposures(exitReason) {
    Array.from(activeResultExposures.keys()).forEach(rank => {
        endResultExposure(rank, exitReason);
    });
}

function logResultExposure() {
    if (!("IntersectionObserver" in window)) return;

    const searchResults = document.querySelectorAll("article.content-section");
    if (!searchResults || searchResults.length === 0) return;

    resultExposureObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const rank = entry.target.id.split("-")[1];
            if (entry.isIntersecting && entry.intersectionRatio >= RESULT_EXPOSURE_THRESHOLD) {
                startResultExposure(entry.target);
            } else {
                endResultExposure(rank, "viewport-exit");
            }
        });
    }, { threshold: [0, RESULT_EXPOSURE_THRESHOLD] });

    searchResults.forEach(result => resultExposureObserver.observe(result));
}

function logNoResults() {
    const noResults = document.querySelector("[data-log-no-results='true']");
    if (!noResults || noResults.dataset.logged === "true") return;
    noResults.dataset.logged = "true";

    studyLogger.logEvent("searchNoResults", {
        query: noResults.dataset.query || "",
        rawQuery: noResults.dataset.rawQuery || noResults.dataset.query || "",
        sanitizedQuery: noResults.dataset.sanitizedQuery || noResults.dataset.query || "",
        page: noResults.dataset.page || ""
    });

    const didYouMean = document.getElementById("did-you-mean");
    if(didYouMean){
        console.log("Generated Did You Mean");
        studyLogger.logEvent("generatedDidYouMean", {
            query: noResults.dataset.query || "",
            rawQuery: noResults.dataset.rawQuery || noResults.dataset.query || "",
            sanitizedQuery: noResults.dataset.sanitizedQuery || noResults.dataset.query || "",
            "suggested query": didYouMean.textContent,
            "query_correction_model": didYouMean.getAttribute("source")
        });

        didYouMean.addEventListener("mouseenter", (e) => {
            studyLogger.logEvent("hoverOverDidYouMean", {
                query: noResults.dataset.query || "",
                rawQuery: noResults.dataset.rawQuery || noResults.dataset.query || "",
                sanitizedQuery: noResults.dataset.sanitizedQuery || noResults.dataset.query || "",
                "suggested query": didYouMean.textContent,
                "query_correction_model": didYouMean.getAttribute("source")
            });
        });

        didYouMean.addEventListener("click", (e) => {
            studyLogger.logEvent("clickedDidYouMeanSuggestion", {
                query: noResults.dataset.query || "",
                rawQuery: noResults.dataset.rawQuery || noResults.dataset.query || "",
                sanitizedQuery: noResults.dataset.sanitizedQuery || noResults.dataset.query || "",
                "suggested query": didYouMean.textContent,
                "query_correction_model": didYouMean.getAttribute("source")
            });
        });
    }
}

function logSERP() {
    const searchResults = document.querySelectorAll("article.content-section");
    if (!searchResults || searchResults.length === 0) return; // DOM not ready

    const firstResult = document.querySelector("article.content-section");
    const query = firstResult.getAttribute("query");
    const page = firstResult.getAttribute("page");
    const rawQuery = firstResult.dataset.rawQuery || query;
    const sanitizedQuery = firstResult.dataset.sanitizedQuery || query;
    const searchAppLocation = getSearchAppLocation(query, page);
    const fromURL = studyLogger.checkHistory(searchAppLocation);

    if(fromURL){
        studyLogger.removeHistory();
        studyLogger.addHistory(searchAppLocation);
    }
    else{
        studyLogger.addHistory(searchAppLocation);
        const didYouMean = document.getElementById("did-you-mean");
        if(didYouMean){
            studyLogger.logEvent("generatedDidYouMean", {
                "user query": query,
                rawQuery,
                sanitizedQuery,
                "suggested query": didYouMean.textContent,
                "query_correction_model": didYouMean.getAttribute("source")
            });
        }
        searchResults.forEach(result => {
            const rank = result.id.split("-")[1];
            const details = getResultDetails(rank);
            if (!details) return;
            
            studyLogger.logEvent("searchResultGenerated", {
                    query: details.query,
                    rawQuery: details.rawQuery,
                    sanitizedQuery: details.sanitizedQuery,
                    docid: details.docid,
                    title: details.title,
                    snippet: details.snippet,
                    rank: details.rank,
                    page: details.page,
                    url: details.url,
                    windowLocation: details.windowLocation,
                    // history: studyLogger.getHistory(),
                });
            });
        }

    const didYouMean = document.getElementById("did-you-mean");
    if(didYouMean){
        didYouMean.addEventListener("mouseenter", (e) => {
            studyLogger.logEvent("hoverOverDidYouMean", {
                "user query": query,
                rawQuery,
                sanitizedQuery,
                "suggested query": didYouMean.textContent,
                "query_correction_model": didYouMean.getAttribute("source")
            });
        });

        didYouMean.addEventListener("click", (e) => {
            studyLogger.logEvent("clickedDidYouMeanSuggestion", {
                "user query": query,
                rawQuery,
                sanitizedQuery,
                "suggested query": didYouMean.textContent,
                "query_correction_model": didYouMean.getAttribute("source")
            });
        });
    }
}

// cursorEnteredSnippet / cursorLeftSnippet are desktop-only signals; iPad/touch will not fire mouseenter/mouseleave reliably.
function logMouseHovers(){
    const searchSnippets = document.querySelectorAll("article.content-section");
    if(searchSnippets){
            searchSnippets.forEach(result => {
            const rank = result.id.split("-")[1];

            result.addEventListener("mouseenter", ()=>{
                const details = getResultDetails(rank);
                if (!details) return;
                studyLogger.logEvent("cursorEnteredSnippet", {
                    query: details.query,
                    rawQuery: details.rawQuery,
                    sanitizedQuery: details.sanitizedQuery,
                    docid: details.docid,
                    rank: details.rank,
                    page: details.page,
                    url: details.url,
                    windowLocation: details.windowLocation,
                    // history: studyLogger.getHistory(),
                });
            });

            result.addEventListener("mouseleave", ()=>{
                const details = getResultDetails(rank);
                if (!details) return;
                studyLogger.logEvent("cursorLeftSnippet", {
                    query: details.query,
                    rawQuery: details.rawQuery,
                    sanitizedQuery: details.sanitizedQuery,
                    docid: details.docid,
                    rank: details.rank,
                    page: details.page,
                    url: details.url,
                    windowLocation: details.windowLocation,
                    // history: studyLogger.getHistory(),
                });
            });
        });
    }
}


function logClicks(){
    const resultLinks = document.querySelectorAll("a.result-link");
    if (resultLinks) {
        // const serpContainer = document.getElementsByClassName("container-info");
        resultLinks.forEach(link => {
            link.addEventListener("click", (e) => {
                const rank = getResultRank(link);
                const details = getResultDetails(rank);
                if (!details) return;

                endResultExposure(rank, "result-click");
                flushActiveResultExposures("linkWasVisibleInSerpResults");
                studyLogger.addHistory(details.navigationUrl);
                studyLogger.logEvent("clickedResult", {
                    query: details.query,
                    rawQuery: details.rawQuery,
                    sanitizedQuery: details.sanitizedQuery,
                    docid: details.docid,
                    rank: details.rank,
                    page: details.page,
                    url: details.url,
                    windowLocation: details.windowLocation,
                    navigationUrl: details.navigationUrl,
                });

            });
        });
    }
}

function logPageNavigation(){
    const pageLinks = document.querySelectorAll("a.page-link");
    if (pageLinks) {
        pageLinks.forEach(link => {
        link.addEventListener("click", (e) => {
            flushActiveResultExposures("pagination");
            const clickedLabel = link.textContent.trim();
            const currentPage = parseInt(document.querySelector(".page-item.active a")?.textContent || "0", 10);
            const nextPage = getTargetPage(clickedLabel, currentPage, link);
            const context = getCurrentSearchContext();
            studyLogger.logEvent("pageNavigationClicked", {
                query: context.query,
                rawQuery: context.rawQuery,
                sanitizedQuery: context.sanitizedQuery,
                clicked: clickedLabel,
                fromPage: currentPage,
                toPage: nextPage,
                targetURL: link.href || link.getAttribute("href") || ""
            });
        });
        });

    }
}

let listenersAttached = false;
let serpInitialized = false;

function loggingSearchActions(isPageShow = false){
    if (window.__SOLBrowserBackRecoveryInProgress) return;

    // When restored from BFCache, re-sync logger state from localStorage
    if (isPageShow) {
        studyLogger.init();
    }

    // A BFCache restore retains this DOM and its listeners. Re-syncing stored
    // state must not emit its results again or attach did-you-mean handlers a
    // second time. A fresh page gets a fresh flag and the usual SERP logging.
    if (!serpInitialized) {
        logSERP();
        serpInitialized = true;
    }

    // Only attach event listeners once to prevent duplicates
    if (!listenersAttached) {
        logClicks();
        logMouseHovers();
        logPageNavigation();
        logResultExposure();
        listenersAttached = true;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (window.__SOLBrowserBackRecoveryInProgress) return;

    logNoResults();
    loggingSearchActions(false);
});

window.addEventListener("pageshow", (e) => {
    if (window.__SOLBrowserBackRecoveryInProgress) return;

    if (e.persisted) {
        loggingSearchActions(true);
    }
});

window.addEventListener("pagehide", (e) => {
    flushActiveResultExposures("pagehide");
    if (!e.persisted) {
        listenersAttached = false;
    }
});

window.flushActiveResultExposures = flushActiveResultExposures;
window.__SOLLoggerInternals = {
    getPageType,
    getReturnMetadata,
    getTargetPage: (label, current, href = "") => getTargetPage(
        label,
        current,
        href ? { href, getAttribute: () => href } : null
    ),
};

const endno = document.getElementById("no-end-btn")
if (endno) {
    endno.addEventListener("click", () => {
        studyLogger.logEvent("TaskContinued");
    });
}

const serpBackBtn = document.getElementById("serp-back-btn");
if (serpBackBtn) {
    serpBackBtn.addEventListener("click", () => {
        studyLogger.logEvent(
            "customBackButtonClicked",
            getBackButtonNavigationDetails(serpBackBtn, "serp")
        );
    });
}

const viewerBackBtn = document.getElementById("viewer-back-btn");
if (viewerBackBtn) {
    viewerBackBtn.addEventListener("click", () => {
        studyLogger.logEvent(
            "customBackButtonClicked",
            getBackButtonNavigationDetails(viewerBackBtn, "webpage")
        );
    });
}

const serpLogoLink = document.getElementById("serp-logo-link");
if (serpLogoLink) {
    serpLogoLink.addEventListener("click", () => {
        studyLogger.logEvent("logoOnSerpClicked", {
            fromURL: window.location.href,
            toURL: serpLogoLink.href,
            returnType: "logoToSearch"
        });
    });
}


const taskHelpBtn = document.getElementById("task-help-btn");
const taskHelpModal = document.getElementById("task-help-modal");
const taskHelpCloseBtn = document.getElementById("task-help-close-btn");

if (taskHelpBtn && taskHelpModal) {
    const taskHelpPayload = () => {
        const payload = { fromURL: window.location.href };
        const tn = taskHelpBtn.dataset.taskNumber;
        if (tn) payload.task_number = Number(tn);
        return payload;
    };

    taskHelpBtn.addEventListener("click", () => {
        taskHelpModal.style.display = "flex";
        studyLogger.logEvent("taskQuestionHelpClicked", taskHelpPayload());
    });

    if (taskHelpCloseBtn) {
        taskHelpCloseBtn.addEventListener("click", () => {
            taskHelpModal.style.display = "none";
            studyLogger.logEvent("taskQuestionHelpClosed", taskHelpPayload());
        });
    }
}

const firstAnswerBtn = document.getElementById("search-first-answer-btn");
const firstAnswerDialog = document.getElementById("search-first-answer-dialog");
if (firstAnswerBtn && firstAnswerDialog) {
    let firstAnswerOpen = false;
    const firstAnswerPayload = () => ({
        fromURL: window.location.href, outcome: firstAnswerBtn.dataset.outcome, answerPhase: "pre-search"
    });
    const recordFirstAnswerClosed = reason => {
        if (!firstAnswerOpen) return;
        firstAnswerOpen = false;
        studyLogger.logEvent("firstAnswerClosed", {...firstAnswerPayload(), reason});
    };
    const closeFirstAnswer = reason => {
        if (!firstAnswerDialog.open) return;
        firstAnswerDialog.close(reason);
        recordFirstAnswerClosed(reason);
    };
    firstAnswerBtn.addEventListener("click", () => {
        if (window.taskEndLockout || firstAnswerDialog.open) return;
        firstAnswerDialog.returnValue = "";
        firstAnswerDialog.showModal();
        firstAnswerOpen = true;
        studyLogger.logEvent("firstAnswerOpened", firstAnswerPayload());
    });
    document.getElementById("search-first-answer-close").addEventListener("click", () => {
        closeFirstAnswer("button");
    });
    firstAnswerDialog.addEventListener("cancel", event => {
        event.preventDefault();
        closeFirstAnswer("escape");
    });
    firstAnswerDialog.addEventListener("close", () => {
        if (firstAnswerDialog.open) return; // Ignore a queued close from before a restored page reopened it.
        recordFirstAnswerClosed(firstAnswerDialog.returnValue || "escape");
        firstAnswerBtn.focus();
    });
    firstAnswerDialog.addEventListener("click", event => {
        const bounds = firstAnswerDialog.getBoundingClientRect();
        if (event.target === firstAnswerDialog && (event.clientX < bounds.left || event.clientX > bounds.right
                || event.clientY < bounds.top || event.clientY > bounds.bottom)) {
            closeFirstAnswer("backdrop");
        }
    });
    window.addEventListener("pagehide", () => {
        if (firstAnswerDialog.open) closeFirstAnswer("pagehide");
        else recordFirstAnswerClosed(firstAnswerDialog.returnValue || "pagehide");
    });
}

// Upload while the child works, not only when a task ends: an interrupted run
// (lesson over, iPad switched off, the next child starting on this iPad) keeps
// everything up to the last page. Each batch keeps its identifier until it is
// acknowledged, so a retry never writes events twice. Failures stay queued for
// the next trigger and for the end of the task, which reports them.
function syncLogsInBackground() {
    // Only events of the run the server issued to this page; never after the
    // end of a task or the experiment has cleared the client data.
    if (!window.SESSION_ID || studyLogger.sessionID !== window.SESSION_ID) return;
    studyLogger.sendLogs().catch((error) => console.warn("Background upload will be retried:", error));
}

const BACKGROUND_UPLOAD_INTERVAL_MS = 60000;

window.addEventListener("load", () => {
    syncLogsInBackground();
    setInterval(syncLogsInBackground, BACKGROUND_UPLOAD_INTERVAL_MS);
    // Registered after the page's own pagehide handlers (for example the viewer's
    // webpageClosed event), so leaving the page includes them.
    window.addEventListener("pagehide", syncLogsInBackground);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") syncLogsInBackground();
    });
});
