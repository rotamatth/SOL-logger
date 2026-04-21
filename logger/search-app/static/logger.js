(() => {

    // Fallback UUID generator for browsers without crypto.randomUUID()
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            const r = Math.random() * 16 | 0,
                  v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    const logger = {
        sessionID: null,
        logs: [],
        historyTracker: [],

        // Restore previous logger state from localStorage or create a new session
        init() {
            const uuid = (typeof crypto !== 'undefined' && crypto.randomUUID)
                ? crypto.randomUUID()
                : generateUUID();

            this.sessionID = localStorage.getItem('sessionID') || uuid;
            localStorage.setItem('sessionID', this.sessionID);

            const storedLogs = localStorage.getItem('sessionLogs');
            const browserHistory = localStorage.getItem('browserHistory');
            this.logs = storedLogs ? JSON.parse(storedLogs) : [];
            this.historyTracker = browserHistory ? JSON.parse(browserHistory) : [];
        },
        
        // Create one log entry and persist it locally immediately
        logEvent(type, details = {}) {
            const event = {
                type,
                timestamp: new Date().toISOString(),
                sessionID: this.sessionID,
                ...details
            };
            console.log("[LOG]", event);
            this.logs.push(event);
            localStorage.setItem('sessionLogs', JSON.stringify(this.logs));
        },

        // Track visited pages/results to reconstruct navigation behavior
        addHistory(url) {
            this.historyTracker.push(url);
            localStorage.setItem('browserHistory', JSON.stringify(this.historyTracker));
        },

        // Detect a back-navigation pattern by comparing current and previous URLs
        checkHistory(url) {
            if (this.historyTracker.length <= 1) return;
            
            prevPage = this.historyTracker[this.historyTracker.length - 2];
            if (url==prevPage) return this.historyTracker[this.historyTracker.length - 1];
            else return;
        },

        // Remove the last back-and-forth pair once it has been logged
        removeHistory(){
            this.historyTracker.splice(this.historyTracker.length-2, 2);
            localStorage.setItem('browserHistory', JSON.stringify(this.historyTracker));
        },

        // Debug/helper view of current history stack
        getHistory() {
            return JSON.stringify(this.historyTracker);
        },

        // Send collected logs to the Flask backend and clear local state if successful
        sendLogs() {
            if (this.logs.length === 0) return;

            return fetch('/log_session', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    session_id: this.sessionID,
                    logs: this.logs
                })
            }).then(response => {
                if (response.ok) {
                    console.log('Logs successfully sent to server.');
                    localStorage.removeItem('sessionLogs');
                    localStorage.removeItem('sessionID');
                    localStorage.removeItem('browserHistory');
                    this.logs = [];
                    this.historyTracker = [];
                } else {
                    console.error('Failed to send logs.');
                }
            });
        }
    };

    // Initialize once and expose globally so templates can call studyLogger
    logger.init();
    window.studyLogger = logger;
})();

// Log the submitted participant ID at the start of the study
const idform = document.getElementById("enter-id-form");
if (idform) {
  idform.addEventListener("submit", (e) => {
    const uid = document.getElementById("id-box").value;
    studyLogger.logEvent("idSubmitted", { uid });
  });
}

// Log the start of a task once the user confirms/enters it
const taskbtn = document.getElementById("task-btn")
if (taskbtn) {
    taskbtn.addEventListener("click", () => {
        studyLogger.logEvent("TaskStarted");
    });
}

// Capture when the user focuses the search box
const searchbox = document.getElementById("search-box")
if (searchbox) {
    searchbox.addEventListener("focus", () => {
        studyLogger.logEvent("queryBoxFocused");
    });
}

// Log each submitted query before the search request is processed
const searchbar = document.getElementById("search-bar")
if (searchbar) {
    searchbar.addEventListener("submit", (e) => {
        const query = document.getElementById("search-box").value;
        studyLogger.logEvent("querySubmitted", { 
            query: query, 
        });
    }); 
}

// Rebuild the internal search-app URL for a given query/page pair
function getSearchAppLocation(query, page){
    const search_params = new URLSearchParams();
    search_params.set("query", query);
    search_params.set("page", page);
    return window.location.origin + "/result?" + search_params.toString();
}

function logSERP() {
    const searchResults = document.querySelectorAll("article.content-section");
    if (!searchResults || searchResults.length === 0) return; // No SERP on this page

    // Use the first result to recover page-level context
    const firstResult = document.querySelector("article.content-section");
    const query = firstResult.getAttribute("query");
    const  page = firstResult.getAttribute("page");
    const searchAppLocation = getSearchAppLocation(query, page);

    // If this SERP was revisited via back navigation, log it differently
    if(studyLogger.checkHistory(searchAppLocation)){
        studyLogger.logEvent("wentBack", {
            "query": query,
            "fromURL": studyLogger.checkHistory(searchAppLocation),
            "toURL": searchAppLocation,
        });
        studyLogger.removeHistory();
        studyLogger.addHistory(searchAppLocation);
    }
    else{
        // First visit to this SERP: log every generated result item
        studyLogger.addHistory(searchAppLocation);
        const didYouMean = document.getElementById("did-you-mean");
        if(didYouMean){
            studyLogger.logEvent("Query suggestion generated", {
                "user query": query,
                "suggested query": didYouMean.textContent
            });

            didYouMean.addEventListener("click", (e) => {
                studyLogger.logEvent("clickedQuerySuggestion", {
                    "user query": query,
                    "suggested query": didYouMean.textContent
                });
            });
        }
        searchResults.forEach(result => {
            const query = result.getAttribute("query");
            const docid = result.getAttribute("base_ir");
            const rank = result.id.split("-")[1];
            const page = result.getAttribute("page");
            const url = document.getElementById(`abstract-link-${rank}`).getAttribute("href");
            const searchAppLocation = getSearchAppLocation(query, page);
            
            studyLogger.logEvent("searchResultGenerated", {
                    query: query,
                    docid: docid,
                    rank: rank,
                    page: page,
                    url: url,
                    windowLocation: searchAppLocation,
                    // history: studyLogger.getHistory(),
                });
        });
    }
}

function logMouseHovers(){
    const searchSnippets = document.querySelectorAll("article.content-section");
    if(searchSnippets){
            // Log hover enter/leave to approximate attention on each result
            searchSnippets.forEach(result => {
            const query = result.getAttribute("query");
            const docid = result.getAttribute("base_ir");
            const rank = result.id.split("-")[1];
            const page = result.getAttribute("page");
            const url = document.getElementById(`abstract-link-${rank}`).getAttribute("href");
            const searchAppLocation = getSearchAppLocation(query, page);

            result.addEventListener("mouseenter", ()=>{           
                studyLogger.logEvent("cursorEnteredSnippet", {
                    query: query,
                    docid: docid,
                    rank: rank,
                    page: page,
                    url: url,
                    windowLocation: searchAppLocation,
                    // history: studyLogger.getHistory(),
                });
            });

            result.addEventListener("mouseleave", ()=>{            
                studyLogger.logEvent("cursorLeftSnippet", {
                    query: query,
                    docid: docid,
                    rank: rank,
                    page: page,
                    url: url,
                    windowLocation: searchAppLocation,
                    // history: studyLogger.getHistory(),
                });
            });           
        });
    }
}


function logClicks(){
    const resultLinks = document.querySelectorAll("a.result-link");
    if (resultLinks) {
        // Log which result was clicked and save the target URL in history
        resultLinks.forEach(link => {
            link.addEventListener("click", (e) => {
                const rank = link.id.split("-")[2];
                const url = link.getAttribute("href");
                const snippet = document.getElementById(`result-${rank}`);
                const query = snippet.getAttribute("query");
                const page = snippet.getAttribute("page");
                const docid = document.getElementById(`result-${rank}`).getAttribute("base_ir");
                
                studyLogger.addHistory(url);
                studyLogger.logEvent("clickedResult", {
                    query: query,
                    docid: docid,
                    rank: rank,
                    page: page,
                    url: url,
                    windowLocation: url,
                    // history: studyLogger.getHistory(),
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
            const clickedLabel = link.textContent.trim();
            const currentPage = parseInt(document.querySelector(".page-item.active a")?.textContent || "0", 10);
            const nextPage = getTargetPage(clickedLabel, currentPage);
            studyLogger.logEvent("pageNavigationClicked", {
            clicked: clickedLabel,
            fromPage: currentPage,
            toPage: nextPage
            });
        });
        });

        // Infer target page from pagination label text
        function getTargetPage(label, current) {
        if (label.includes("Next")) return current + 1;
        if (label.includes("Previous")) return current - 1;
        const num = parseInt(label, 10);
        return isNaN(num) ? null : num;
        }
    }
}

let listenersAttached = false;

function loggingSearchActions(isPageShow = false){
    // When restored from BFCache, re-sync logger state from localStorage
    if (isPageShow) {
        studyLogger.init();
    }

    logSERP();

    // Only attach event listeners once to prevent duplicates
    if (!listenersAttached) {
        logClicks();
        logMouseHovers();
        logPageNavigation();
        listenersAttached = true;
    }
}

document.addEventListener("DOMContentLoaded", () => loggingSearchActions(false));

window.addEventListener("pageshow", (e) => {
    if (e.persisted) {
        // Page restored from BFCache - re-run SERP logging for back detection
        loggingSearchActions(true);
    }
});

// Fallback for browsers that don't use BFCache but still have back navigation issues
window.addEventListener("pagehide", (e) => {
    // Reset flag so listeners are re-attached if page is reloaded fresh
    if (!e.persisted) {
        listenersAttached = false;
    }
});

// Log explicit return to the app home page
const homeButton = document.getElementById("app-home");
if (homeButton) {
    homeButton.addEventListener("click", ()=>{
        studyLogger.logEvent("wentBackHome");
    });
}

// Log click on the "end task" entry action
endtask = document.getElementById("end-task-btn")
if (endtask) {
    endtask.addEventListener("click", () => {
        studyLogger.logEvent("ClickedEndTask");
    });
}

// Log confirmation of task termination
endyes = document.getElementById("yes-end-btn")
if (endyes) {
    endyes.addEventListener("click", () => {
        studyLogger.logEvent("TaskEndConfirmed");
    });
}

// Log final feedback reason before ending the task
feedbackbtn = document.getElementById("feedback-btn")
if (feedbackbtn) {
    feedbackbtn.addEventListener("click", () => {
        const fb = document.getElementById("textarea_feedback").value;
        studyLogger.logEvent("TaskEnded", {
            answer: fb
        });
    });
}

// Log cancellation of the end-task action
endno = document.getElementById("no-end-btn")
if (endno) {
    endno.addEventListener("click", () => {
        studyLogger.logEvent("TaskContinued");
    });
}
