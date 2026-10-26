import json

from .test_logging_contract import run_logger_node_script


def test_lost_ack_retries_exact_request_and_preserves_events_arriving_during_upload():
    result = run_logger_node_script('''
        (async () => {
            let next = 0;
            crypto.randomUUID = () => `batch-${++next}`;
            studyLogger.logEvent("TaskEnded", {answer: "rain"});
            const requests = [];
            global.fetch = async (_url, options) => {
                requests.push(options.body);
                if (requests.length === 1) throw new Error("response lost after server saved");
                const batch = JSON.parse(options.body);
                return {ok: true, json: async () => ({status: "logged", batch_id: batch.batch_id})};
            };
            try { await studyLogger.sendLogs(); } catch (_) {}
            if (studyLogger.logs.length !== 1) throw new Error("Failed upload lost its buffer");
            studyLogger.logEvent("resourceViewEnded");
            await studyLogger.sendLogs();
            if (requests[0] !== requests[1]) throw new Error("Retry changed the original batch");
            if (JSON.parse(requests[2]).logs[0].type !== "resourceViewEnded") throw new Error("New event was not retained");
            if (studyLogger.logs.length !== 0) throw new Error("Acknowledged events remained queued");
            console.log(JSON.stringify({requests: requests.length, remaining: studyLogger.logs.length}));
        })().catch(error => { console.error(error); process.exitCode = 1; });
    ''')
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {"requests": 3, "remaining": 0}


def test_invalid_ack_does_not_discard_pending_upload():
    result = run_logger_node_script('''
        (async () => {
            studyLogger.logEvent("TaskEnded", {answer: "rain"});
            global.fetch = async () => ({ok: true, json: async () => ({status: "logged", batch_id: "wrong"})});
            let rejected = false;
            try { await studyLogger.sendLogs(); } catch (_) { rejected = true; }
            if (!rejected || studyLogger.logs.length !== 1) throw new Error("Unverified acknowledgement cleared data");
            if (!localStorage.getItem(`solPendingUpload:${studyLogger.sessionID}`)) throw new Error("Pending request was lost");
            console.log("preserved");
        })().catch(error => { console.error(error); process.exitCode = 1; });
    ''')
    assert result.stdout.strip().endswith("preserved")
