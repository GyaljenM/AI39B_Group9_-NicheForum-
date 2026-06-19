/* DEPRECATED — do not use.
 *
 * The live scoreboard now lives in app/static/liveScores.js and fetches our own
 * /api/live endpoint (a server-side proxy to football-data.org). This old copy
 * called football-data.org directly from the browser, which fails on CORS and
 * leaked the API token into client-side code.
 *
 * This file is not served (Flask serves from app/static/). Kept empty on purpose
 * so no stale token or broken fetch loop ships to browsers.
 */
