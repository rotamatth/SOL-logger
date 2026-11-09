"""A permanent test experiment for developers, kept apart from the study's results.

Each test ID is an experiment with one participant, itself. It can start on any day and
as often as needed, and every start is a new attempt. Its logs go to their own folder
inside the log directory, which the dashboard's scan of real runs never enters. It needs
no session, enrollment or settings change, so it cannot change a class, a session number
or a child's results.
"""
from copy import deepcopy
import secrets

from .participants import school_year_for
from .study_config import question_set_topics

TEST_RUNS_FOLDER = "test-runs"
TEST_SOURCE = "test"


def _question_set(theme, rows):
    return {"theme": theme, "approved": True, "metadata": {"origin": "permanent-test"},
            "questions": [{"id": f"test-{theme}-{number}", "topic": topic, "question": question}
                          for number, (topic, question) in enumerate(rows, 1)]}


# In the order of their animations: a question's position chooses its clip and poster. The questions are
# those of the 10 November 2026 sessions, 4a spazio and 5a orecchio, as the server stored them on 9 November.
TEST_EXPERIMENTS = {
    "TEST-spazio": _question_set("spazio", (
        ("Sistema solare Giove", "Come si chiamano i satelliti maggiori di Giove?"),
        ("Primo animale nello spazio", "Qual è stato il primo animale nello spazio e come si chiamava?"),
        ("Altre galassie", "Quali sono i nomi di altre 3 galassie oltre la nostra?"))),
    "TEST-orecchio": _question_set("orecchio", (
        ("Fact-finding -- Ossicini Orecchio", "Quali sono i 3 ossicini dentro al nostro orecchio?"),
        ("Multi-step -- Coclea", "Che forma ha la coclea e dove si trova?"),
        ("Open-ended -- animali", "Quali sono 5 animali con l'udito più sviluppato al mondo?"))),
}


def is_test_participant(uid):
    return isinstance(uid, str) and uid in TEST_EXPERIMENTS


def is_test_log_name(name):
    """A test ID's file that reached the real folder inside a child's batch."""
    return name.split("_", 1)[0] in TEST_EXPERIMENTS


def assignment_for_test_id(uid, today):
    """The same shape as a scheduled assignment, with a session of its own for every start."""
    question_set = deepcopy(TEST_EXPERIMENTS[uid])
    theme = question_set["theme"]
    study_session = {"id": f"test-{theme}-{secrets.token_hex(8)}", "name": f"Prova {theme}",
                     "date": today.isoformat(), "theme": theme, "number": 1,
                     "school_year": school_year_for(today.isoformat())}
    return {"session": study_session, "question_set": question_set, "topics": question_set_topics(question_set),
            "source": TEST_SOURCE}
