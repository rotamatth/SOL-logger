(() => {


    // Fallback-UUID-Function for outdated browsers
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

        addHistory(url) {
            this.historyTracker.push(url);
            localStorage.setItem('browserHistory', JSON.stringify(this.historyTracker));
        },

        checkHistory(url) {
            if (this.historyTracker.length <= 1) return;
            
            prevPage = this.historyTracker[this.historyTracker.length - 2];
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

    logger.init();
    window.studyLogger = logger;
})();

const idform = document.getElementById("enter-id-form");
if (idform) {
  idform.addEventListener("submit", (e) => {
    const uid = document.getElementById("id-box").value;
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
if (searchbox) {
    searchbox.addEventListener("focus", () => {
        studyLogger.logEvent("queryBoxFocused");
    });

    // searchbox.addEventListener("change", ()=>{
    //     const value = searchbox.value;
    //     if(window.autoCompleteSuggestions && window.autoCompleteSuggestions.includes(value)){
    //         studyLogger.logEvent("choseAutoCompleteSuggestion", {
    //             "selectedSuggestion": value
    //         });
    //     }
    // });
}

const querySuggestionsList = document.getElementById("query-suggestions");
if(querySuggestionsList){
    querySuggestionsList.addEventListener("mouseover", (e) => {
    const li = e.target.closest("li");
    if (!li) return;

    studyLogger.logEvent("hoverOverQuerySuggestions", {
            query: searchbox?.value || "",
            hoveredSuggestion: li.textContent,
        });
    });
    
    querySuggestionsList.addEventListener("pointerdown", (e) => {
        const li = e.target.closest("li");
        if (!li) return;

        const value = li.textContent;

        if (window.autoCompleteSuggestions && window.autoCompleteSuggestions.includes(value)) {
            studyLogger.logEvent("choseAutoCompleteSuggestion", {
                selectedSuggestion: value
            });
        }
    });

}


// const querySuggestionsBox = document.getElementById("query-suggestions-box");
// if(querySuggestionsBox){
//     querySuggestionsBox.addEventListener("mouseenter", ()=>{
//         studyLogger.logEvent("hoverOverQuerySuggestions", {
//             query: "query"
//         });
//     });
// } 

const searchbar = document.getElementById("search-bar")
if (searchbar) {
    searchbar.addEventListener("submit", (e) => {
        const query = document.getElementById("search-box").value;
        studyLogger.logEvent("querySubmitted", { 
            query: query, 
        });
    }); 
}

function getSearchAppLocation(query, page){
    const search_params = new URLSearchParams();
    search_params.set("query", query);
    search_params.set("page", page);
    return window.location.origin + "/result?" + search_params.toString();
}

function logSERP() {
    const searchResults = document.querySelectorAll("article.content-section");
    if (!searchResults || searchResults.length === 0) return; // DOM not ready

    const firstResult = document.querySelector("article.content-section");
    const query = firstResult.getAttribute("query");
    const page = firstResult.getAttribute("page");
    const searchAppLocation = getSearchAppLocation(query, page);

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
        studyLogger.addHistory(searchAppLocation);
        const didYouMean = document.getElementById("did-you-mean");
        if(didYouMean){
            studyLogger.logEvent("generatedDidYouMean", {
                "user query": query,
                "suggested query": didYouMean.textContent
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

    const didYouMean = document.getElementById("did-you-mean");
    if(didYouMean){
        didYouMean.addEventListener("mouseenter", (e) => {
            studyLogger.logEvent("hoverOverDidYouMean", {
                "user query": query,
                "suggested query": didYouMean.textContent
            });
        });

        didYouMean.addEventListener("click", (e) => {
            studyLogger.logEvent("clickedDidYouMeanSuggestion", {
                "user query": query,
                "suggested query": didYouMean.textContent
            });
        });
    }
}

function logMouseHovers(){
    const searchSnippets = document.querySelectorAll("article.content-section");
    if(searchSnippets){
            searchSnippets.forEach(result => {
            const query = result.getAttribute("query");
            const docid = result.getAttribute("base_ir");
            const rank = result.id.split("-")[1];
            const page = result.getAttribute("page");
            const url = document.getElementById(`abstract-link-${rank}`).getAttribute("href");
            const searchAppLocation = getSearchAppLocation(query, page);

            result.addEventListener("mouseenter", ()=>{           
                studyLogger.logEvent("hoverOverSnippet", {
                    query: query,
                    docid: docid,
                    rank: rank,
                    page: page,
                    url: url,
                    windowLocation: searchAppLocation,
                    // history: studyLogger.getHistory(),
                });
            });

            // result.addEventListener("mouseleave", ()=>{            
            //     studyLogger.logEvent("cursorLeftSnippet", {
            //         query: query,
            //         docid: docid,
            //         rank: rank,
            //         page: page,
            //         url: url,
            //         windowLocation: searchAppLocation,
            //         // history: studyLogger.getHistory(),
            //     });
            // });           
        });
    }
}


function logClicks(){
    const resultLinks = document.querySelectorAll("a.result-link");
    if (resultLinks) {
        // const serpContainer = document.getElementsByClassName("container-info");
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

const homeButton = document.getElementById("app-home");
homeButton.addEventListener("click", ()=>{
    studyLogger.logEvent("wentBackHome");
});


endtask = document.getElementById("end-task-btn")
if (endtask) {
    endtask.addEventListener("click", () => {
        studyLogger.logEvent("ClickedEndTask");
    });
}

endyes = document.getElementById("yes-end-btn")
if (endyes) {
    endyes.addEventListener("click", () => {
        studyLogger.logEvent("TaskEndConfirmed");
    });
}

feedbackbtn = document.getElementById("feedback-btn")
if (feedbackbtn) {
    feedbackbtn.addEventListener("click", () => {
        const fb = document.getElementById("textarea_feedback").value;
        studyLogger.logEvent("TaskEnded", {
            answer: fb
        });
    });
}

endno = document.getElementById("no-end-btn")
if (endno) {
    endno.addEventListener("click", () => {
        studyLogger.logEvent("TaskContinued");
    });
}

