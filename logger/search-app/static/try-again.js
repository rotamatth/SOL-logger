// A tablet can reuse a connection the server is just closing, and the request then fails at once
// without reaching the server. Try again before troubling the child.
window.tryAgain = async function tryAgain(attempt) {
  for (const delay of [300, 1000, 3000]) {
    try {
      return await attempt();
    } catch (_) {
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  return attempt();
};
